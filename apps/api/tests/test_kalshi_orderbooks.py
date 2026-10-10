from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from edgeeagle_api.local_kalshi import create_local_kalshi_orderbook_app
from edgeeagle_api.main import create_app
from edgeeagle_domain.provenance import DataSourceId, VenueId
from edgeeagle_domain.raw import RawCapture, RawPayload, RawPayloadIntegrityError
from edgeeagle_ingestion.kalshi_orderbook import (
    KalshiOrderBookCandidate,
    KalshiOrderBookManifest,
    normalize_kalshi_orderbook,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE_DIR = ROOT / "tests/fixtures/providers/kalshi/orderbook-v1"
TICKER = "EE-SYNTH-2026"
SOURCE_ID = DataSourceId("kalshi_api")
VENUE_ID = VenueId("kalshi")
SNAPSHOT_AT = datetime(2026, 10, 9, 16, tzinfo=UTC)


def fixture_candidate() -> KalshiOrderBookCandidate:
    body = (FIXTURE_DIR / "orderbook.json").read_bytes()
    raw = RawPayload(
        capture=RawCapture(
            data_source_id=SOURCE_ID,
            resource=f"/trade-api/v2/markets/{TICKER}/orderbook",
            ingested_at=SNAPSHOT_AT,
        ),
        body=body,
    ).reference()
    store = Mock()
    store.get.return_value = body
    manifest = KalshiOrderBookManifest(
        raw=raw,
        market_ticker=TICKER,
        venue_id=VENUE_ID,
        simulated_snapshot_at=SNAPSHOT_AT,
    )
    return normalize_kalshi_orderbook(store, manifest)


def test_default_orderbook_api_is_unconfigured_and_read_only() -> None:
    with TestClient(create_app()) as client:
        response = client.get(f"/v1/provider-order-books/{SOURCE_ID.value}/{TICKER}")
        assert response.status_code == 503
        assert response.headers["cache-control"] == "no-store"
        assert (
            client.post(f"/v1/provider-order-books/{SOURCE_ID.value}/{TICKER}").status_code == 405
        )


def test_configured_orderbook_api_returns_exact_unmapped_fixture() -> None:
    candidate = fixture_candidate()
    reads = Mock(return_value=candidate)
    with TestClient(create_app(orderbook_reads=reads)) as client:
        response = client.get(f"/v1/provider-order-books/{SOURCE_ID.value}/{TICKER}")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json() == {
            "data_source_id": "kalshi_api",
            "venue_id": "kalshi",
            "market_ticker": TICKER,
            "snapshot_at": "2026-10-09T16:00:00Z",
            "historical_availability": "UNKNOWN",
            "mapping_status": "UNMAPPED",
            "usage": "SYNTHETIC_ONLY",
            "parser_version": candidate.parser_version,
            "normalizer_version": candidate.normalizer_version,
            "raw": {
                "sha256": candidate.raw.sha256,
                "size_bytes": candidate.raw.size_bytes,
                "resource": candidate.raw.capture.resource,
                "ingested_at": "2026-10-09T16:00:00Z",
                "effective_at": None,
                "observed_at": None,
                "available_at": None,
            },
            "yes_bids": [
                {"price_dollars": "0.1200", "contract_count": "8"},
                {"price_dollars": "0.305", "contract_count": "2.50"},
            ],
            "no_bids": [{"price_dollars": "0.410", "contract_count": "3.25"}],
        }
        reads.assert_called_once_with(SOURCE_ID.value, TICKER)


def test_unknown_source_or_ticker_is_not_found() -> None:
    reads = Mock(return_value=None)
    with TestClient(create_app(orderbook_reads=reads)) as client:
        assert client.get(f"/v1/provider-order-books/other/{TICKER}").status_code == 404
        assert client.get(f"/v1/provider-order-books/{SOURCE_ID.value}/OTHER").status_code == 404


@pytest.mark.parametrize(
    "failure",
    [
        FileNotFoundError("private path"),
        ValueError("bad fixture"),
        RawPayloadIntegrityError("private checksum"),
    ],
)
def test_orderbook_api_sanitizes_retained_fixture_failures(failure: Exception) -> None:
    reads = Mock(side_effect=failure)
    with TestClient(create_app(orderbook_reads=reads), raise_server_exceptions=False) as client:
        response = client.get(f"/v1/provider-order-books/{SOURCE_ID.value}/{TICKER}")
        assert response.status_code == 503
        assert "private path" not in response.text
        assert "bad fixture" not in response.text
        assert response.headers["cache-control"] == "no-store"


def test_local_fixture_factory_rechecks_pinned_bytes_on_every_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("edgeeagle_api.local_kalshi.FIXTURE_DIRECTORY", tmp_path)
    (tmp_path / "metadata.json").write_bytes((FIXTURE_DIR / "metadata.json").read_bytes())
    payload_path = tmp_path / "orderbook.json"
    payload_path.write_bytes((FIXTURE_DIR / "orderbook.json").read_bytes())
    app = create_local_kalshi_orderbook_app()
    with TestClient(app) as client:
        path = f"/v1/provider-order-books/{SOURCE_ID.value}/{TICKER}"
        assert client.get(path).status_code == 200
        payload_path.write_text("{}")
        failed = client.get(path)
        assert failed.status_code == 503
        assert "sha256" not in failed.text
        payload_path.write_bytes((FIXTURE_DIR / "orderbook.json").read_bytes())
        (tmp_path / "metadata.json").write_text("{}")
        assert client.get(path).status_code == 503


def test_openapi_exposes_get_only_orderbook_contract() -> None:
    with TestClient(create_app()) as client:
        operation = client.get("/openapi.json").json()["paths"][
            "/v1/provider-order-books/{dataSourceId}/{marketTicker}"
        ]
        assert set(operation) == {"get"}
        assert operation["get"]["operationId"] == "get_provider_order_book"


@pytest.mark.parametrize(
    "path",
    [
        f"/v1/provider-order-books/%20/{TICKER}",
        f"/v1/provider-order-books/{SOURCE_ID.value}/lowercase",
        f"/v1/provider-order-books/{SOURCE_ID.value}/{'A' * 129}",
    ],
)
def test_invalid_source_and_ticker_path_values_are_rejected(path: str) -> None:
    with TestClient(create_app(orderbook_reads=Mock())) as client:
        assert client.get(path).status_code == 422
