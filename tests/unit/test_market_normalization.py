import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import Mock

import pytest

from edgeeagle_domain.provenance import DataSource, SourceType, Venue, VenueId, VenueType
from edgeeagle_domain.raw import RawPayloadIntegrityError
from edgeeagle_ingestion.synthetic_markets import (
    MarketFixtureBinding,
    VenueBinding,
    normalize_market_fixture,
    replay_market_fixture,
)
from tests.unit.test_event_normalization import binding, fixture_payload


def context() -> MarketFixtureBinding:
    b = binding()
    return MarketFixtureBinding(
        event=b,
        starts_at=datetime(2026, 10, 1, 18, tzinfo=UTC),
        source=DataSource(
            data_source_id=b.key.data_source_id,
            code="SYNTHETIC",
            source_type=SourceType.ODDS_AGGREGATOR,
            capabilities=frozenset({"SYNTHETIC_FIXTURE"}),
        ),
        venues=(
            VenueBinding(
                provider_key="bovada",
                venue=Venue(
                    venue_id=VenueId("synthetic-book"),
                    operator="Synthetic",
                    product="Test",
                    jurisdiction="TEST",
                    venue_type=VenueType.SPORTSBOOK,
                    capabilities=frozenset(),
                ),
            ),
        ),
    )


def test_retained_normalization_is_exact_and_read_only() -> None:
    raw, store = fixture_payload(), Mock()
    store.get.return_value = raw.body
    result = normalize_market_fixture(store, raw.reference(), (context(),))
    assert result == normalize_market_fixture(store, raw.reference(), (context(),))
    assert len(result) == 1
    candidate = result[0]
    assert candidate.raw == raw.reference()
    assert candidate.binding == context()
    assert {q.odds_decimal for q in candidate.quotes} == {
        Decimal("2.1"),
        Decimal("3.4"),
        Decimal("3.2"),
    }
    assert len({q.quote_id for q in candidate.quotes}) == 3
    assert all(q.available_at is None and q.provider_quote_id is None for q in candidate.quotes)
    assert all(q.observed_at == datetime(2026, 9, 22, 12, tzinfo=UTC) for q in candidate.quotes)
    assert all(q.venue_id == VenueId("synthetic-book") for q in candidate.quotes)
    assert all(q.data_source_id == raw.capture.data_source_id for q in candidate.quotes)
    store.put.assert_not_called()


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "unsupported", "bad_price", "bad_time", "unknown_team"]
)
def test_bad_final_market_fails_whole_capture(mutation: str) -> None:
    raw = fixture_payload()
    rows = json.loads(raw.body)
    market = rows[0]["bookmakers"][0]["markets"][0]
    if mutation == "missing":
        market["outcomes"].pop()
    elif mutation == "duplicate":
        market["outcomes"][2] = market["outcomes"][0]
    elif mutation == "unsupported":
        market["key"] = "totals"
    elif mutation == "bad_price":
        market["outcomes"][2]["price"] = True
    elif mutation == "bad_time":
        market["last_update"] = "2026-09-22"
    else:
        market["outcomes"][2]["name"] = "Other"
    raw = replace(raw, body=json.dumps(rows).encode())
    store = Mock()
    store.get.return_value = raw.body
    with pytest.raises(ValueError):
        normalize_market_fixture(store, raw.reference(), (context(),))
    store.put.assert_not_called()


def test_integrity_missing_raw_and_context_guards() -> None:
    raw, store = fixture_payload(), Mock()
    store.get.return_value = None
    with pytest.raises(FileNotFoundError):
        normalize_market_fixture(store, raw.reference(), (context(),))
    store.get.return_value = b"[]"
    with pytest.raises(RawPayloadIntegrityError):
        normalize_market_fixture(store, raw.reference(), (context(),))
    store.get.return_value = raw.body
    for bindings in (
        (),
        (context(), context()),
        (replace(context(), starts_at=datetime(2026, 10, 2, tzinfo=UTC)),),
    ):
        with pytest.raises(ValueError):
            normalize_market_fixture(store, raw.reference(), bindings)


def test_non_synthetic_source_and_venue_aliases_rejected() -> None:
    c = context()
    with pytest.raises(ValueError):
        replace(c, source=replace(c.source, capabilities=frozenset()))
    with pytest.raises(ValueError):
        replace(c, venues=(c.venues[0], replace(c.venues[0], provider_key="other")))


def test_replay_rejects_projection_drift_without_reading_current_state() -> None:
    raw, store = fixture_payload(), Mock()
    store.get.return_value = raw.body
    result = normalize_market_fixture(store, raw.reference(), (context(),))
    assert replay_market_fixture(store, result) == result
    first = result[0]
    changed = replace(
        first, quotes=(replace(first.quotes[0], odds_decimal=Decimal("9")), *first.quotes[1:])
    )
    assert changed.quotes[0].quote_id == first.quotes[0].quote_id
    with pytest.raises(ValueError, match="projection"):
        replay_market_fixture(store, (changed,))
    for invalid in ((), result * 2):
        with pytest.raises(ValueError):
            replay_market_fixture(store, invalid)
    store.put.assert_not_called()


@pytest.mark.parametrize(
    "body",
    [b"null", b"[]", b"[null]", b"{}", b"[NaN]", b"[{}]", b'[{"id":"x","id":"y"}]', b"\xff", b"["],
)
def test_malformed_payloads_are_rejected(body: bytes) -> None:
    raw, store = replace(fixture_payload(), body=body), Mock()
    store.get.return_value = body
    with pytest.raises(ValueError):
        normalize_market_fixture(store, raw.reference(), (context(),))


def test_capture_identity_and_no_timestamp_fallback() -> None:
    raw, store = fixture_payload(), Mock()
    store.get.return_value = raw.body
    initial = normalize_market_fixture(store, raw.reference(), (context(),))[0]
    newer = replace(
        raw, capture=replace(raw.capture, ingested_at=datetime(2026, 9, 23, tzinfo=UTC))
    )
    later = normalize_market_fixture(store, newer.reference(), (context(),))[0]
    assert later.market == initial.market and later.selections == initial.selections
    assert {q.quote_id for q in initial.quotes}.isdisjoint(q.quote_id for q in later.quotes)
    rows = json.loads(raw.body)
    del rows[0]["bookmakers"][0]["markets"][0]["last_update"]
    changed = replace(raw, body=json.dumps(rows).encode())
    store.get.return_value = changed.body
    result = normalize_market_fixture(store, changed.reference(), (context(),))[0]
    assert all(q.observed_at is None for q in result.quotes)


@pytest.mark.parametrize("kind", ["event", "bookmaker", "market", "missing_bookmaker"])
def test_duplicate_and_incomplete_collection_guards(kind: str) -> None:
    rows = json.loads(fixture_payload().body)
    if kind == "event":
        rows *= 2
    elif kind == "bookmaker":
        rows[0]["bookmakers"] *= 2
    elif kind == "market":
        rows[0]["bookmakers"][0]["markets"] *= 2
    else:
        rows[0]["bookmakers"] = []
    raw, store = replace(fixture_payload(), body=json.dumps(rows).encode()), Mock()
    store.get.return_value = raw.body
    with pytest.raises(ValueError):
        normalize_market_fixture(store, raw.reference(), (context(),))


def test_size_guard_precedes_storage_read() -> None:
    store = Mock()
    raw = replace(fixture_payload().reference(), size_bytes=1024 * 1024 + 1)
    with pytest.raises(ValueError):
        normalize_market_fixture(store, raw, (context(),))
    store.get.assert_not_called()
