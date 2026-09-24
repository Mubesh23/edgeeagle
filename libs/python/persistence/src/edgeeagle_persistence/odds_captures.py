"""Retained Odds API projection reads; application acceptance is rolled out separately."""

import re
from typing import Any

from sqlalchemy import Connection, text

from edgeeagle_ingestion.market_acceptance import MarketAcceptanceConflict
from edgeeagle_ingestion.odds_normalization import NormalizedOddsCapture, _identity_seed
from edgeeagle_ingestion.odds_receipts import decode_odds_receipt, encode_odds_receipt
from edgeeagle_persistence._transactions import require_transaction


def capture_identity(capture: NormalizedOddsCapture) -> str:
    return _identity_seed(capture.manifest)


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
