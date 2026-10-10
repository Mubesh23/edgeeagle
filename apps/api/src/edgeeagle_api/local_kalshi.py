"""Explicit local composition for the single authored Kalshi order-book fixture."""

import json
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI

from edgeeagle_api.main import create_app
from edgeeagle_domain.provenance import DataSourceId, VenueId
from edgeeagle_domain.raw import (
    RawCapture,
    RawPayload,
    RawPayloadReference,
    RawPayloadStore,
)
from edgeeagle_ingestion.kalshi_orderbook import (
    KalshiOrderBookCandidate,
    KalshiOrderBookManifest,
    normalize_kalshi_orderbook,
)

FIXTURE_DIRECTORY = (
    Path(__file__).resolve().parents[4] / "tests/fixtures/providers/kalshi/orderbook-v1"
)
DATA_SOURCE_ID = DataSourceId("kalshi_api")
VENUE_ID = VenueId("kalshi")


class _FixtureFileStore(RawPayloadStore):
    def __init__(self, path: Path, reference: RawPayloadReference) -> None:
        self._path = path
        self._reference = reference

    def get(self, reference: RawPayloadReference) -> bytes | None:
        if reference != self._reference:
            return None
        return self._path.read_bytes()

    def put(self, payload: RawPayload) -> RawPayloadReference:
        raise PermissionError("authored fixture store is read-only")


def _manifest(directory: Path) -> KalshiOrderBookManifest:
    metadata = json.loads((directory / "metadata.json").read_text(encoding="utf-8"))
    if (
        not isinstance(metadata, dict)
        or metadata.get("provider") != "KALSHI"
        or metadata.get("origin") != "AUTHORED_FIXTURE"
        or metadata.get("endpoint") != "/trade-api/v2/markets/EE-SYNTH-2026/orderbook"
        or metadata.get("sha256")
        != "e696a0d1045a548f0959b5637ea46610348a0b8cc0ed069e8218add0facd32c0"
        or type(metadata.get("size_bytes")) is not int
        or metadata.get("size_bytes") != 141
        or not isinstance(metadata.get("simulated_snapshot_at"), str)
    ):
        raise ValueError("unsupported authored Kalshi fixture metadata")
    ticker = "EE-SYNTH-2026"
    snapshot = datetime.fromisoformat(metadata["simulated_snapshot_at"])
    capture = RawCapture(
        data_source_id=DATA_SOURCE_ID,
        resource=metadata["endpoint"],
        ingested_at=snapshot,
    )
    reference = RawPayloadReference(
        capture=capture,
        sha256=metadata["sha256"],
        size_bytes=metadata["size_bytes"],
    )
    return KalshiOrderBookManifest(
        raw=reference,
        market_ticker=ticker,
        venue_id=VENUE_ID,
        simulated_snapshot_at=snapshot,
    )


def create_local_kalshi_orderbook_app() -> FastAPI:
    """Expose a pinned synthetic fixture only; invoke Uvicorn on loopback."""

    def reads(data_source_id: str, market_ticker: str) -> KalshiOrderBookCandidate | None:
        if (data_source_id, market_ticker) != (
            DATA_SOURCE_ID.value,
            "EE-SYNTH-2026",
        ):
            return None
        manifest = _manifest(FIXTURE_DIRECTORY)
        store = _FixtureFileStore(FIXTURE_DIRECTORY / "orderbook.json", manifest.raw)
        return normalize_kalshi_orderbook(store, manifest)

    return create_app(orderbook_reads=reads)
