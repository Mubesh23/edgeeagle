"""Immutable whole-capture Odds API acceptance and verified projection reads."""

import re
from typing import Any

from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from edgeeagle_domain.provenance import SourceType
from edgeeagle_ingestion.market_acceptance import MarketAcceptanceConflict
from edgeeagle_ingestion.odds_acceptance import capture_identity as capture_identity
from edgeeagle_ingestion.odds_normalization import NormalizedOddsCapture
from edgeeagle_ingestion.odds_receipts import decode_odds_receipt, encode_odds_receipt
from edgeeagle_persistence._transactions import require_transaction
from edgeeagle_persistence.mappings import PostgresMappingRepository
from edgeeagle_persistence.provenance import PostgresDataSourceRepository, PostgresVenueRepository
from edgeeagle_persistence.sports import PostgresSportsRepository


def projection_rows(capture: NormalizedOddsCapture) -> list[tuple[str, str, dict[str, Any]]]:
    identity = capture_identity(capture)
    rows: list[tuple[str, str, dict[str, Any]]] = []
    for observation in capture.observations:
        market = observation.market
        rows.append(
            (
                "markets",
                "market_id",
                {
                    "market_id": market.market_id.value,
                    "event_id": market.event_id.value,
                    "market_type": market.market_type.value,
                    "period": market.period.value,
                },
            )
        )
        for selection in observation.selections:
            rows.append(
                (
                    "market_selections",
                    "selection_id",
                    {
                        "selection_id": selection.selection_id.value,
                        "market_id": selection.market_id.value,
                        "outcome": selection.outcome.value,
                        "participant_id": selection.participant_id.value
                        if selection.participant_id
                        else None,
                    },
                )
            )
    rows.append(
        (
            "odds_capture_receipts",
            "capture_id",
            {
                "capture_id": identity,
                "data_source_id": capture.manifest.raw.capture.data_source_id.value,
                "snapshot": encode_odds_receipt(capture).decode("ascii"),
            },
        )
    )
    for observation in capture.observations:
        for quote in observation.quotes:
            rows.append(
                (
                    "odds_capture_quotes",
                    "quote_id",
                    {
                        "quote_id": quote.quote_id.value,
                        "capture_id": identity,
                        "selection_id": quote.selection_id.value,
                        "market_id": observation.market.market_id.value,
                        "data_source_id": quote.data_source_id.value,
                        "venue_id": quote.venue_id.value,
                        "odds_decimal": quote.odds_decimal,
                        "ingested_at": quote.ingested_at,
                        "observed_at": quote.observed_at,
                    },
                )
            )
    return rows


class PostgresOddsCaptureReader:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def compare(self, table: str, key: str, values: dict[str, Any]) -> None:
        # Identifiers come only from projection_rows, never request data.
        row = (
            self._connection.execute(
                text(f"SELECT {', '.join(values)} FROM {table} WHERE {key} = :id"),
                {"id": values[key]},
            )
            .mappings()
            .one_or_none()
        )
        if row is None or dict(row) != values:
            raise MarketAcceptanceConflict("Stored Odds API projection differs from receipt")

    def get(self, identity: str) -> NormalizedOddsCapture | None:
        require_transaction(self._connection)
        if not isinstance(identity, str) or not re.fullmatch(r"[0-9a-f]{64}", identity):
            raise ValueError("capture identity must be a SHA-256 digest")
        body = self._connection.scalar(
            text("SELECT snapshot FROM odds_capture_receipts WHERE capture_id = :id"),
            {"id": identity},
        )
        if body is None:
            return None
        capture = decode_odds_receipt(body.encode("ascii"))
        if capture_identity(capture) != identity:
            raise MarketAcceptanceConflict("Stored capture identity differs from manifest")
        for table, key, values in projection_rows(capture):
            self.compare(table, key, values)
        count = self._connection.scalar(
            text("SELECT count(*) FROM odds_capture_quotes WHERE capture_id = :id"),
            {"id": identity},
        )
        if count != sum(len(o.quotes) for o in capture.observations):
            raise MarketAcceptanceConflict("Stored capture quote coverage differs")
        return capture


class PostgresOddsCaptureRepository(PostgresOddsCaptureReader):
    def _references(self, capture: NormalizedOddsCapture) -> None:
        sports = PostgresSportsRepository(self._connection)
        sources = PostgresDataSourceRepository(self._connection)
        venues = PostgresVenueRepository(self._connection)
        mappings = PostgresMappingRepository(self._connection)
        source = sources.get(capture.manifest.raw.capture.data_source_id)
        if (
            source is None
            or source.code != "THE_ODDS_API"
            or source.source_type is not SourceType.ODDS_AGGREGATOR
        ):
            raise MarketAcceptanceConflict("The Odds API aggregator source is missing or differs")
        for evidence in capture.evidence:
            r = evidence.references
            if (
                sources.get(r.source.data_source_id) != r.source
                or sports.get_sport(r.sport.sport_id) != r.sport
                or sports.get_competition(r.competition.competition_id) != r.competition
                or sports.get_season(r.season.season_id) != r.season
                or sports.get_participant(r.home.participant_id) != r.home
                or sports.get_participant(r.away.participant_id) != r.away
                or sports.get_event(r.event.event_id) != r.event
                or set(sports.get_event_participants(r.event.event_id)) != set(r.entries)
                or any(venues.get(v.venue_id) != v for v in r.venues)
            ):
                raise MarketAcceptanceConflict("Canonical Odds API context differs or is missing")
            # Verify selected immutable evidence exists; never re-resolve a later mapping.
            if any(revision not in mappings.history(revision.key) for revision in r.revisions):
                raise MarketAcceptanceConflict("Retained mapping evidence is missing or differs")

    def accept(self, capture: NormalizedOddsCapture) -> int:
        require_transaction(self._connection)
        if self._connection.get_isolation_level() != "READ COMMITTED":
            raise ValueError("Odds acceptance requires READ COMMITTED")
        body = encode_odds_receipt(capture)
        value = decode_odds_receipt(body)
        identity = capture_identity(value)
        inserted = 0
        try:
            with self._connection.begin_nested():
                for event_id in sorted({e.references.event.event_id.value for e in value.evidence}):
                    if (
                        self._connection.scalar(
                            text("SELECT event_id FROM events WHERE event_id = :id FOR UPDATE"),
                            {"id": event_id},
                        )
                        is None
                    ):
                        raise MarketAcceptanceConflict("Canonical event is missing")
                existing = self.get(identity)
                if existing is not None:
                    if encode_odds_receipt(existing) != body:
                        raise MarketAcceptanceConflict("Conflicting Odds API capture replay")
                    return 0
                self._references(value)
                for table, key, row in projection_rows(value):
                    result = self._connection.scalar(
                        text(
                            f"INSERT INTO {table} ({', '.join(row)}) VALUES "
                            f"({', '.join(':' + name for name in row)}) "
                            f"ON CONFLICT DO NOTHING RETURNING {key}"
                        ),
                        row,
                    )
                    if table == "odds_capture_receipts" and result is not None:
                        inserted = 1
                    self.compare(table, key, row)
                if self.get(identity) != value:
                    raise MarketAcceptanceConflict("Accepted capture differs on readback")
        except IntegrityError as exc:
            raise MarketAcceptanceConflict("Odds acceptance violates stored constraints") from exc
        return inserted
