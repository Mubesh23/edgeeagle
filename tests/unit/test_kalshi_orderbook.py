import hashlib
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

import pytest

from edgeeagle_domain.markets import BinaryOrderBook, OrderBookLevel
from edgeeagle_domain.provenance import DataSourceId, VenueId
from edgeeagle_domain.raw import RawCapture, RawPayload, RawPayloadIntegrityError
from edgeeagle_ingestion.kalshi_orderbook import (
    NORMALIZER_VERSION,
    PARSER_VERSION,
    KalshiOrderBookManifest,
    normalize_kalshi_orderbook,
    replay_kalshi_orderbook,
)

NOW = datetime(2026, 10, 9, 16, tzinfo=UTC)
FIXTURE = Path("tests/fixtures/providers/kalshi/orderbook-v1/orderbook.json")
TICKER = "EE-SYNTH-2026"


def retained(body: bytes | None = None) -> tuple[Mock, KalshiOrderBookManifest]:
    content = FIXTURE.read_bytes() if body is None else body
    raw = RawPayload(
        capture=RawCapture(
            data_source_id=DataSourceId("kalshi_api"),
            resource=f"/trade-api/v2/markets/{TICKER}/orderbook",
            ingested_at=NOW,
        ),
        body=content,
    ).reference()
    store = Mock()
    store.get.return_value = content
    return store, KalshiOrderBookManifest(
        raw=raw, market_ticker=TICKER, venue_id=VenueId("kalshi"), simulated_snapshot_at=NOW
    )


def test_normalizes_exact_fixed_point_levels_without_inference() -> None:
    store, manifest = retained()
    result = normalize_kalshi_orderbook(store, manifest)
    assert result.order_book == BinaryOrderBook(
        yes_bids=(
            OrderBookLevel(price_dollars=Decimal("0.1200"), contract_count=Decimal("8")),
            OrderBookLevel(price_dollars=Decimal("0.305"), contract_count=Decimal("2.50")),
        ),
        no_bids=(OrderBookLevel(price_dollars=Decimal("0.410"), contract_count=Decimal("3.25")),),
    )
    assert result.market_ticker == TICKER
    assert result.data_source_id == DataSourceId("kalshi_api")
    assert result.venue_id == VenueId("kalshi")
    assert result.raw == manifest.raw
    assert result.snapshot_at == NOW
    assert result.usage == "SYNTHETIC_ONLY"
    assert result.parser_version == PARSER_VERSION
    assert result.normalizer_version == NORMALIZER_VERSION
    store.get.assert_called_once_with(manifest.raw)
    store.put.assert_not_called()
    with pytest.raises(FrozenInstanceError):
        result.market_ticker = "OTHER"  # type: ignore[misc]


def test_empty_sides_and_replay_are_deterministic() -> None:
    body = b'{"orderbook_fp":{"yes_dollars":[],"no_dollars":[]}}'
    store, manifest = retained(body)
    result = normalize_kalshi_orderbook(store, manifest)
    assert result.order_book == BinaryOrderBook(yes_bids=(), no_bids=())
    store.get.reset_mock()
    assert replay_kalshi_orderbook(store, result) == result
    store.get.assert_called_once_with(manifest.raw)


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b'{"orderbook_fp":{"yes_dollars":[],"yes_dollars":[],"no_dollars":[]}}',
        b'{"orderbook_fp":{"yes_dollars":[],"no_dollars":[],"extra":1}}',
        b'{"orderbook_fp":{"yes_dollars":[[0.5,"1"]],"no_dollars":[]}}',
        b'{"orderbook_fp":{"yes_dollars":[["0.5","1","2"]],"no_dollars":[]}}',
        b'{"orderbook_fp":{"yes_dollars":[["NaN","1"]],"no_dollars":[]}}',
        b'{"orderbook_fp":{"yes_dollars":[["1.01","1"]],"no_dollars":[]}}',
        b'{"orderbook_fp":{"yes_dollars":[["0.5","0"]],"no_dollars":[]}}',
        b'{"orderbook_fp":{"yes_dollars":[["0.5","1"],["0.5","2"]],"no_dollars":[]}}',
        b'{"orderbook_fp":{"yes_dollars":[["0.6","1"],["0.5","2"]],"no_dollars":[]}}',
        b'{"orderbook_fp":{"yes_dollars":[],"no_dollars":[],"unexpected":[]}}',
        b'{"orderbook_fp":{"yes_dollars":[],"no_dollars":[]},"unexpected":true}',
        b'{"orderbook_fp":{"yes_dollars":[],"no_dollars":[]}} trailing',
        b"[" * 1100 + b"]" * 1100,
    ],
)
def test_rejects_malformed_or_unsupported_payload(body: bytes) -> None:
    store, manifest = retained(body)
    store.get.return_value = body
    manifest = replace(
        manifest,
        raw=replace(manifest.raw, sha256=hashlib.sha256(body).hexdigest(), size_bytes=len(body)),
    )
    with pytest.raises((ValueError, TypeError)):
        normalize_kalshi_orderbook(store, manifest)


def test_rejects_identity_context_and_integrity_mismatch() -> None:
    store, manifest = retained()
    with pytest.raises(ValueError):
        normalize_kalshi_orderbook(store, replace(manifest, market_ticker="OTHER"))
    with pytest.raises(ValueError):
        normalize_kalshi_orderbook(
            store, replace(manifest, simulated_snapshot_at=NOW.replace(tzinfo=None))
        )
    store.get.return_value = b"{}"
    with pytest.raises(RawPayloadIntegrityError):
        normalize_kalshi_orderbook(store, manifest)
    store.get.return_value = None
    with pytest.raises(FileNotFoundError):
        normalize_kalshi_orderbook(store, manifest)


def test_replay_detects_changed_retained_projection() -> None:
    store, manifest = retained()
    result = normalize_kalshi_orderbook(store, manifest)
    changed = b'{"orderbook_fp":{"yes_dollars":[],"no_dollars":[]}}'
    store.get.return_value = changed
    with pytest.raises(RawPayloadIntegrityError):
        replay_kalshi_orderbook(store, result)
