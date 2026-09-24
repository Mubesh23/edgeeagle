"""Strict whole-capture Odds API receipt v2; separate from legacy market v1."""

import json
import types
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from functools import lru_cache
from typing import Any, Literal, get_args, get_origin, get_type_hints

from edgeeagle_domain._validation import aware_datetime

from .market_receipts import _scalar as _decimal_scalar
from .odds_api_parser import PARSER_VERSION, NativeOddsBookmaker, NativeOddsEvent, NativeOddsOutcome
from .odds_normalization import (
    NORMALIZER_VERSION,
    NormalizedOddsCapture,
    _project,
)

MAX_RECEIPT_BYTES = 8 * 1024 * 1024


@lru_cache(maxsize=64)
def _hints(cls: type) -> dict[str, Any]:
    # Only classes reachable from the statically selected root schema are used.
    # Payload tags never select imports, classes or executable code.
    return get_type_hints(cls)


def _encode(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            "$type": type(value).__name__,
            **{f.name: _encode(getattr(value, f.name)) for f in fields(value)},
        }
    if isinstance(value, datetime):
        aware_datetime(value, "receipt timestamp")
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Decimal):
        return _decimal_scalar(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_encode(v) for v in value]
    if isinstance(value, frozenset):
        return sorted(value)
    if value is None or type(value) in (str, int, bool):
        return value
    raise ValueError("unsupported receipt value")


def _decode(expected: Any, value: Any, depth: int = 0) -> Any:
    if depth > 32:
        raise ValueError("receipt nesting exceeds limit")
    origin, args = get_origin(expected), get_args(expected)
    if origin is types.UnionType:
        for option in args:
            try:
                return _decode(option, value, depth + 1)
            except (ValueError, TypeError):
                pass
        raise ValueError("receipt union type mismatch")
    if origin is Literal:
        if not any(type(value) is type(option) and value == option for option in args):
            raise ValueError("unsupported receipt literal")
        return value
    if origin in (tuple, frozenset):
        if not isinstance(value, list) or len(value) > 6000:
            raise ValueError("invalid receipt collection")
        items = tuple(_decode(args[0], item, depth + 1) for item in value)
        if origin is frozenset:
            if len(set(items)) != len(items):
                raise ValueError("duplicate set members")
            return frozenset(items)
        return items
    if isinstance(expected, type) and is_dataclass(expected):
        hints = _hints(expected)
        if (
            not isinstance(value, dict)
            or set(value) != {"$type", *hints}
            or value["$type"] != expected.__name__
        ):
            raise ValueError("invalid typed receipt record")
        return expected(
            **{name: _decode(kind, value[name], depth + 1) for name, kind in hints.items()}
        )
    if expected is datetime:
        if not isinstance(value, str):
            raise ValueError("receipt timestamp must be text")
        parsed = datetime.fromisoformat(value)
        aware_datetime(parsed, "receipt timestamp")
        return parsed.astimezone(UTC)
    if expected is Decimal:
        if not isinstance(value, str) or len(value) > 1024:
            raise ValueError("receipt decimal must be bounded exact text")
        number = Decimal(value)
        if not number.is_finite():
            raise ValueError("nonfinite receipt decimal")
        return number
    if isinstance(expected, type) and issubclass(expected, Enum):
        return expected(value)
    if expected in (str, int, bool, type(None)) and type(value) is expected:
        return value
    raise ValueError("invalid receipt scalar")


def _validate(capture: NormalizedOddsCapture) -> None:
    if capture.parser_version != PARSER_VERSION or capture.normalizer_version != NORMALIZER_VERSION:
        raise ValueError("unsupported odds receipt versions")
    if len(capture.evidence) > 100 or len(capture.observations) > 2000:
        raise ValueError("odds capture exceeds bounds")
    observations = {(o.provider_event_id, o.bookmaker_key): o for o in capture.observations}
    if len(observations) != len(capture.observations):
        raise ValueError("duplicate odds observations")
    native = []
    for evidence in capture.evidence:
        guard, refs = evidence.guard, evidence.references
        books = []
        for revision in refs.revisions[2:]:
            key = revision.key.provider_entity_id
            obs = observations.get((guard.event_key.provider_entity_id, key))
            outcomes = []
            book_time = market_time = None
            if obs is not None:
                if len(obs.selections) != 3 or len(obs.quotes) != 3:
                    raise ValueError("receipt must contain complete three-way prices")
                prices = {q.selection_id: q.odds_decimal for q in obs.quotes}
                labels = {"HOME": guard.home_label, "DRAW": "Draw", "AWAY": guard.away_label}
                for selection in obs.selections:
                    outcomes.append(
                        NativeOddsOutcome(
                            labels[selection.outcome.value], prices[selection.selection_id]
                        )
                    )
                book_time, market_time = obs.bookmaker_updated_at, obs.market_updated_at
                for timestamp in (book_time, market_time):
                    if timestamp is not None and timestamp > capture.manifest.snapshot_at:
                        raise ValueError("provider update exceeds snapshot")
            books.append(NativeOddsBookmaker(key, book_time, market_time, tuple(outcomes)))
        native.append(
            NativeOddsEvent(
                guard.event_key.provider_entity_id,
                refs.revisions[0].key.provider_entity_id,
                guard.starts_at,
                guard.home_label,
                guard.away_label,
                tuple(books),
            )
        )
    if sorted(e.guard.event_key.provider_entity_id for e in capture.evidence) != [
        e.event_id for e in native
    ]:
        raise ValueError("noncanonical evidence order")
    if _project(tuple(native), capture.manifest, capture.evidence) != capture:
        raise ValueError("receipt projection is inconsistent")


def _body(capture: NormalizedOddsCapture) -> bytes:
    return json.dumps(
        {"format": 2, "usage": capture.manifest.usage, "capture": _encode(capture)},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def encode_odds_receipt(capture: NormalizedOddsCapture) -> bytes:
    try:
        value = _decode(NormalizedOddsCapture, _encode(capture))
        _validate(value)
        body = _body(value)
        if len(body) > MAX_RECEIPT_BYTES:
            raise ValueError("odds receipt exceeds size limit")
        return body
    except (TypeError, KeyError, AttributeError, RecursionError, ArithmeticError) as exc:
        raise ValueError("invalid odds receipt") from exc


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate receipt key")
        value[key] = item
    return value


def _forbidden(value: str) -> Any:
    raise ValueError("receipt requires exact decimal strings")


def decode_odds_receipt(body: bytes) -> NormalizedOddsCapture:
    if not isinstance(body, bytes) or len(body) > MAX_RECEIPT_BYTES:
        raise ValueError("odds receipt must be bounded bytes")
    try:
        doc = json.loads(
            body, object_pairs_hook=_pairs, parse_float=_forbidden, parse_constant=_forbidden
        )
        if (
            not isinstance(doc, dict)
            or set(doc) != {"format", "usage", "capture"}
            or type(doc["format"]) is not int
            or doc["format"] != 2
        ):
            raise ValueError("invalid odds receipt envelope")
        capture: NormalizedOddsCapture = _decode(NormalizedOddsCapture, doc["capture"])
        _validate(capture)
        if doc["usage"] != capture.manifest.usage or _body(capture) != body:
            raise ValueError("noncanonical odds receipt")
        return capture
    except (
        TypeError,
        KeyError,
        AttributeError,
        UnicodeError,
        RecursionError,
        ArithmeticError,
    ) as exc:
        raise ValueError("invalid odds receipt") from exc
