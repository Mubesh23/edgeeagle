"""Provider-native parsing remains offline and separate from canonical identity."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from edgeeagle_ingestion.odds_api_parser import MAX_BYTES, parse_soccer_h2h

FIXTURE = (
    Path(__file__).parents[1] / "fixtures/providers/the_odds_api/pre-match-v1/odds-success.json"
)
SNAPSHOT = datetime(2026, 9, 23, 12, tzinfo=UTC)


def parse(body: bytes) -> Any:
    return parse_soccer_h2h(body, sport_key="soccer_epl", snapshot_at=SNAPSHOT)


def test_odds_api_parser_preserves_exact_prices_and_bookmaker_timestamp() -> None:
    event = parse(FIXTURE.read_bytes())[0]
    assert event.event_id == "authored-odds-api-event-001"
    assert event.home_team == "Authored Home FC"
    assert event.commence_time == datetime(2026, 10, 1, 18, tzinfo=UTC)
    book = event.bookmakers[0]
    assert book.bookmaker_key == "bovada"
    assert book.bookmaker_updated_at == datetime(2026, 9, 23, 11, 59, tzinfo=UTC)
    assert book.market_updated_at is None
    assert {o.name: o.price for o in book.outcomes}["Authored Home FC"] == Decimal(
        "2.12345678901234567890123456789"
    )


@pytest.mark.parametrize("kind", ["empty", "no-books", "no-markets"])
def test_odds_api_parser_accepts_valid_no_quote_results(kind: str) -> None:
    rows = json.loads(FIXTURE.read_bytes())
    if kind == "empty":
        rows = []
    elif kind == "no-books":
        rows[0]["bookmakers"] = []
    else:
        rows[0]["bookmakers"][0]["markets"] = []
    result = parse(json.dumps(rows).encode())
    assert all(not book.outcomes for event in result for book in event.bookmakers)


@pytest.mark.parametrize(
    "case",
    [
        "duplicate-event",
        "duplicate-book",
        "duplicate-outcome",
        "missing-draw",
        "unknown-outcome",
        "american-price",
        "bool-price",
        "string-price",
        "point",
        "unsupported-market",
        "two-markets",
        "live",
        "at-kickoff",
        "wrong-sport",
        "same-teams",
        "draw-team",
        "naive-time",
        "future-update",
        "bad-market-update",
        "missing-bookmakers",
        "null-books",
        "missing-id",
    ],
)
def test_odds_api_parser_rejects_invalid_capture_without_partial_results(case: str) -> None:
    rows = json.loads(FIXTURE.read_bytes())
    event = rows[0]
    book = event["bookmakers"][0]
    market = book["markets"][0]
    if case == "duplicate-event":
        rows.append(event)
    elif case == "duplicate-book":
        event["bookmakers"].append(book)
    elif case == "duplicate-outcome":
        market["outcomes"][1] = market["outcomes"][0]
    elif case == "missing-draw":
        market["outcomes"].pop(1)
    elif case == "unknown-outcome":
        market["outcomes"][1]["name"] = "Other"
    elif case == "american-price":
        market["outcomes"][0]["price"] = -110
    elif case == "bool-price":
        market["outcomes"][0]["price"] = True
    elif case == "string-price":
        market["outcomes"][0]["price"] = "2.1"
    elif case == "point":
        market["outcomes"][0]["point"] = 0
    elif case == "unsupported-market":
        market["key"] = "h2h_lay"
    elif case == "two-markets":
        book["markets"].append(market)
    elif case == "live":
        event["commence_time"] = "2026-09-23T11:59:59Z"
    elif case == "at-kickoff":
        event["commence_time"] = SNAPSHOT.isoformat()
    elif case == "wrong-sport":
        event["sport_key"] = "soccer_other"
    elif case == "same-teams":
        event["away_team"] = event["home_team"]
    elif case == "draw-team":
        event["home_team"] = "Draw"
    elif case == "naive-time":
        event["commence_time"] = "2026-10-01T18:00:00"
    elif case == "future-update":
        book["last_update"] = "2026-09-23T12:00:01Z"
    elif case == "bad-market-update":
        market["last_update"] = False
    elif case == "missing-bookmakers":
        del event["bookmakers"]
    elif case == "null-books":
        event["bookmakers"] = None
    elif case == "missing-id":
        del event["id"]
    with pytest.raises(ValueError):
        parse(json.dumps(rows).encode())


@pytest.mark.parametrize(
    "body",
    [
        b"{}",
        b"null",
        b"[null]",
        b"invalid",
        b"\xff",
        b'[{"id":"a","id":"b"}]',
        b"[NaN]",
        b"[Infinity]",
        b" " * (MAX_BYTES + 1),
    ],
)
def test_odds_api_parser_rejects_invalid_json_and_size(body: bytes) -> None:
    with pytest.raises(ValueError):
        parse(body)


def test_odds_api_parser_retains_both_scopes_without_inventing_observation_time() -> None:
    rows = json.loads(FIXTURE.read_bytes())
    book = rows[0]["bookmakers"][0]
    del book["last_update"]
    result = parse(json.dumps(rows).encode())[0].bookmakers[0]
    assert result.bookmaker_updated_at is None and result.market_updated_at is None
    book["markets"][0]["last_update"] = "2026-09-23T13:59:00+02:00"
    result = parse(json.dumps(rows).encode())[0].bookmakers[0]
    assert result.bookmaker_updated_at is None
    assert result.market_updated_at == datetime(2026, 9, 23, 11, 59, tzinfo=UTC)


@pytest.mark.parametrize("value", ["", " padded", "a" * 257, "bad\x00id", "bad\ud800id", 5, None])
def test_odds_api_parser_rejects_invalid_native_text(value: object) -> None:
    rows = json.loads(FIXTURE.read_bytes())
    rows[0]["id"] = value
    with pytest.raises(ValueError, match="provider text"):
        parse(json.dumps(rows).encode())


@pytest.mark.parametrize(
    "sport_key", ["upcoming", "basketball_nba", "soccer_", "soccer_epl?key=secret"]
)
def test_odds_api_parser_requires_explicit_soccer_competition(sport_key: str) -> None:
    with pytest.raises(ValueError, match="competition key"):
        parse_soccer_h2h(b"[]", sport_key=sport_key, snapshot_at=SNAPSHOT)


def test_odds_api_parser_enforces_collection_limits_and_aware_cutoff() -> None:
    rows = json.loads(FIXTURE.read_bytes())
    with pytest.raises(ValueError, match="collection size"):
        parse(json.dumps(rows * 101).encode())
    rows[0]["bookmakers"] *= 21
    with pytest.raises(ValueError, match="collection size"):
        parse(json.dumps(rows).encode())
    with pytest.raises(ValueError, match="timezone-aware"):
        parse_soccer_h2h(b"[]", sport_key="soccer_epl", snapshot_at=SNAPSHOT.replace(tzinfo=None))


def test_odds_api_parser_result_order_is_not_provider_array_order() -> None:
    rows = json.loads(FIXTURE.read_bytes())
    second = {**rows[0], "id": "authored-odds-api-event-002"}
    rows.append(second)
    before = parse(json.dumps(rows).encode())
    rows.reverse()
    rows[0]["bookmakers"][0]["markets"][0]["outcomes"].reverse()
    assert parse(json.dumps(rows).encode()) == before
