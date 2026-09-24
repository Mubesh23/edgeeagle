"""Atomic immutable market acceptance in caller-owned PostgreSQL transactions."""

import re
from typing import Any

from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from edgeeagle_ingestion.market_acceptance import (
    MarketAcceptanceConflict,
    canonical_batch,
    receipt_id,
)
from edgeeagle_ingestion.market_receipts import decode_market_receipt, encode_market_receipt
from edgeeagle_ingestion.synthetic_markets import MarketCandidate
from edgeeagle_persistence._transactions import require_transaction
from edgeeagle_persistence.provenance import PostgresDataSourceRepository, PostgresVenueRepository
from edgeeagle_persistence.sports import PostgresSportsRepository


def _rows(candidate: MarketCandidate) -> list[tuple[str, str, dict[str, Any]]]:
    """Trusted SQL identifiers only; all externally supplied values remain parameters."""
    m = candidate.market
    result: list[tuple[str, str, dict[str, Any]]] = [
        (
            "markets",
            "market_id",
            {
                "market_id": m.market_id.value,
                "event_id": m.event_id.value,
                "market_type": m.market_type.value,
                "period": m.period.value,
            },
        )
    ]
    for s in candidate.selections:
        result.append(
            (
                "market_selections",
                "selection_id",
                {
                    "selection_id": s.selection_id.value,
                    "market_id": s.market_id.value,
                    "outcome": s.outcome.value,
                    "participant_id": s.participant_id.value if s.participant_id else None,
                },
            )
        )
    identity = receipt_id(candidate)
    result.append(
        (
            "market_receipts",
            "receipt_id",
            {
                "receipt_id": identity,
                "market_id": m.market_id.value,
                "data_source_id": candidate.raw.capture.data_source_id.value,
                "venue_id": candidate.quotes[0].venue_id.value,
                "snapshot": encode_market_receipt(candidate).decode("ascii"),
            },
        )
    )
    for q in candidate.quotes:
        result.append(
            (
                "market_quotes",
                "quote_id",
                {
                    "quote_id": q.quote_id.value,
                    "receipt_id": identity,
                    "selection_id": q.selection_id.value,
                    "market_id": m.market_id.value,
                    "data_source_id": q.data_source_id.value,
                    "venue_id": q.venue_id.value,
                    "odds_decimal": q.odds_decimal,
                    "ingested_at": q.ingested_at,
                    "observed_at": q.observed_at,
                    "available_at": q.available_at,
                    "effective_at": q.effective_at,
                    "provider_quote_id": q.provider_quote_id,
                },
            )
        )
    return result


class PostgresMarketAcceptanceRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def _compare(self, table: str, key: str, values: dict[str, Any]) -> None:
        row = (
            self._connection.execute(
                text(f"SELECT {', '.join(values)} FROM {table} WHERE {key} = :identity"),
                {"identity": values[key]},
            )
            .mappings()
            .one_or_none()
        )
        if row is None or dict(row) != values:
            raise MarketAcceptanceConflict("Stored market projection differs from retained receipt")

    def get(self, identity: str) -> MarketCandidate | None:
        if not isinstance(identity, str) or not re.fullmatch("[0-9a-f]{64}", identity):
            raise ValueError("receipt identity must be a lowercase SHA-256 digest")
        require_transaction(self._connection)
        body = self._connection.scalar(
            text("SELECT snapshot FROM market_receipts WHERE receipt_id = :id"), {"id": identity}
        )
        if body is None:
            return None
        value = decode_market_receipt(body.encode("ascii"))
        if receipt_id(value) != identity:
            raise MarketAcceptanceConflict("Receipt lineage identity mismatch")
        for table, key, values in _rows(value):
            self._compare(table, key, values)
        if (
            self._connection.scalar(
                text("SELECT count(*) FROM market_quotes WHERE receipt_id = :id"), {"id": identity}
            )
            != 3
        ):
            raise MarketAcceptanceConflict("Receipt quote coverage differs")
        return value

    def _references(self, value: MarketCandidate) -> None:
        b = value.binding
        sports = PostgresSportsRepository(self._connection)
        if (
            sports.get_sport(b.event.sport.sport_id) != b.event.sport
            or sports.get_competition(b.event.competition.competition_id) != b.event.competition
            or sports.get_season(b.event.season.season_id) != b.event.season
            or sports.get_participant(b.event.home.participant_id) != b.event.home
            or sports.get_participant(b.event.away.participant_id) != b.event.away
            or sports.get_event(b.event.event_id) != b.canonical_event
            or set(sports.get_event_participants(b.event.event_id)) != set(b.entries)
            or PostgresDataSourceRepository(self._connection).get(b.source.data_source_id)
            != b.source
        ):
            raise MarketAcceptanceConflict("Canonical reference context differs or is missing")
        venues = PostgresVenueRepository(self._connection)
        if any(venues.get(v.venue.venue_id) != v.venue for v in b.venues):
            raise MarketAcceptanceConflict("Canonical venue context differs or is missing")

    def accept(self, candidates: tuple[MarketCandidate, ...]) -> int:
        require_transaction(self._connection)
        if self._connection.get_isolation_level() != "READ COMMITTED":
            raise ValueError("market acceptance requires READ COMMITTED")
        values = canonical_batch(candidates)
        inserted = 0
        try:
            with self._connection.begin_nested():
                for event_id in sorted({c.market.event_id.value for c in values}):
                    found = self._connection.scalar(
                        text("SELECT event_id FROM events WHERE event_id = :id FOR UPDATE"),
                        {"id": event_id},
                    )
                    if found is None:
                        raise MarketAcceptanceConflict("Canonical event is missing")
                for candidate in values:
                    self._references(candidate)
                    identity = receipt_id(candidate)
                    existing = self.get(identity)
                    if existing is not None:
                        if encode_market_receipt(existing) != encode_market_receipt(candidate):
                            raise MarketAcceptanceConflict("Conflicting market receipt replay")
                        continue
                    for table, key, row in _rows(candidate):
                        self._connection.execute(
                            text(
                                f"INSERT INTO {table} ({', '.join(row)}) VALUES "
                                f"({', '.join(':' + name for name in row)}) ON CONFLICT DO NOTHING"
                            ),
                            row,
                        )
                        self._compare(table, key, row)
                    # Read back and compare every persisted component before success.
                    self.get(identity)
                    inserted += 1
        except IntegrityError as exc:
            raise MarketAcceptanceConflict("Market acceptance violates stored constraints") from exc
        return inserted
