"""Bounded The Odds API v4 soccer h2h parser; native staging, not canonical mapping."""

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, NoReturn

from edgeeagle_domain._validation import aware_datetime

PARSER_VERSION = "the-odds-api-soccer-h2h-json-v1"
MAX_BYTES = 1024 * 1024
MAX_EVENTS = 100
MAX_BOOKMAKERS = 20


@dataclass(frozen=True)
class NativeOddsOutcome:
    name: str
    price: Decimal


@dataclass(frozen=True)
class NativeOddsBookmaker:
    bookmaker_key: str
    bookmaker_updated_at: datetime | None
    market_updated_at: datetime | None
    outcomes: tuple[NativeOddsOutcome, ...]


@dataclass(frozen=True)
class NativeOddsEvent:
    event_id: str
    sport_key: str
    commence_time: datetime
    home_team: str
    away_team: str
    bookmakers: tuple[NativeOddsBookmaker, ...]


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _constant(value: str) -> NoReturn:
    raise ValueError("nonstandard JSON number")


def _text(value: object) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 256
        or value != value.strip()
        or any(ord(character) < 32 or 0xD800 <= ord(character) <= 0xDFFF for character in value)
    ):
        raise ValueError("invalid provider text")
    return value


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("expected provider object")
    return value


def _list(value: object, maximum: int) -> list[Any]:
    if not isinstance(value, list) or len(value) > maximum:
        raise ValueError("invalid provider collection size")
    return value


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})", value
    ):
        raise ValueError("expected aware ISO timestamp")
    return datetime.fromisoformat(value).astimezone(UTC)


def _updated(value: object, snapshot_at: datetime) -> datetime | None:
    if value is None:
        return None
    result = _timestamp(value)
    if result > snapshot_at:
        raise ValueError("provider update exceeds declared capture instant")
    return result


def _bookmaker(value: object, labels: set[str], snapshot_at: datetime) -> NativeOddsBookmaker:
    book = _object(value)
    key = _text(book["key"])
    bookmaker_updated_at = _updated(book.get("last_update"), snapshot_at)
    markets = _list(book["markets"], 1)
    market_updated_at = None
    outcomes = []
    if markets:
        market = _object(markets[0])
        if market["key"] != "h2h":
            raise ValueError("unsupported provider market")
        market_updated_at = _updated(market.get("last_update"), snapshot_at)
        native_outcomes = _list(market["outcomes"], 3)
        if len(native_outcomes) != 3:
            raise ValueError("h2h requires complete HOME/DRAW/AWAY outcomes")
        seen = set()
        for value in native_outcomes:
            native = _object(value)
            name, price = _text(native["name"]), native["price"]
            if name not in labels or name in seen or "point" in native:
                raise ValueError("ambiguous, duplicate or unsupported outcome")
            if not isinstance(price, Decimal) or not price.is_finite() or price <= 1:
                raise ValueError("expected finite decimal odds greater than one")
            seen.add(name)
            outcomes.append(NativeOddsOutcome(name, price))
    return NativeOddsBookmaker(
        key,
        bookmaker_updated_at,
        market_updated_at,
        tuple(sorted(outcomes, key=lambda item: item.name)),
    )


def parse_soccer_h2h(
    body: bytes,
    *,
    sport_key: str,
    snapshot_at: datetime,
) -> tuple[NativeOddsEvent, ...]:
    """Validate the entire response; no partial prefix, mappings or side effects.

    The caller must supply capture evidence (or an explicitly simulated fixture
    instant), not the current clock during replay. Native timestamps retain their
    scope, never imply historical availability. Unknown additive fields stay raw.
    Canonical market period/venue approval belongs to subsequent normalization.
    """
    if not isinstance(body, bytes) or len(body) > MAX_BYTES:
        raise ValueError("provider body must be bounded bytes")
    if not isinstance(sport_key, str) or not re.fullmatch(r"soccer_[a-z0-9_]+", sport_key):
        raise ValueError("require an explicit soccer competition key")
    aware_datetime(snapshot_at, "snapshot_at")
    cutoff = snapshot_at.astimezone(UTC)
    try:
        rows = _list(
            json.loads(
                body.decode("utf-8"),
                parse_float=Decimal,
                parse_int=Decimal,
                parse_constant=_constant,
                object_pairs_hook=_pairs,
            ),
            MAX_EVENTS,
        )
        events, seen = [], set()
        for value in rows:
            row = _object(value)
            identity = _text(row["id"])
            if identity in seen or row["sport_key"] != sport_key:
                raise ValueError("duplicate event or unexpected competition")
            seen.add(identity)
            kickoff = _timestamp(row["commence_time"])
            if kickoff <= cutoff:
                raise ValueError("capture is not strictly pre-match")
            home, away = _text(row["home_team"]), _text(row["away_team"])
            labels = {home, away, "Draw"}
            if len(labels) != 3:
                raise ValueError("ambiguous participant labels")
            books = tuple(
                _bookmaker(b, labels, cutoff) for b in _list(row["bookmakers"], MAX_BOOKMAKERS)
            )
            if len({book.bookmaker_key for book in books}) != len(books):
                raise ValueError("duplicate bookmaker")
            events.append(
                NativeOddsEvent(
                    identity,
                    sport_key,
                    kickoff,
                    home,
                    away,
                    tuple(sorted(books, key=lambda b: b.bookmaker_key)),
                )
            )
        return tuple(sorted(events, key=lambda event: event.event_id))
    except (KeyError, TypeError, UnicodeError, RecursionError, ArithmeticError) as error:
        raise ValueError("malformed provider odds response") from error
