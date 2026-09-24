"""Strict canonical retained market receipt v1; no persistence or provider access."""

import json
from collections.abc import Callable
from dataclasses import asdict, fields, replace
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, TypeVar

from edgeeagle_domain._validation import instance
from edgeeagle_domain.mappings import ProviderEntityKey
from edgeeagle_domain.markets import (
    Market,
    MarketId,
    MarketPeriod,
    MarketType,
    Outcome,
    Quote,
    QuoteId,
    Selection,
    SelectionId,
)
from edgeeagle_domain.provenance import (
    DataSource,
    DataSourceId,
    SourceType,
    Venue,
    VenueId,
    VenueType,
)
from edgeeagle_domain.raw import RawCapture, RawPayloadReference
from edgeeagle_domain.sports import (
    Competition,
    CompetitionId,
    EventId,
    Participant,
    ParticipantId,
    Season,
    SeasonId,
    Sport,
    SportId,
)
from edgeeagle_ingestion.synthetic_events import FixtureEventBinding
from edgeeagle_ingestion.synthetic_markets import (
    NORMALIZER_VERSION,
    PARSER_VERSION,
    MarketCandidate,
    MarketFixtureBinding,
    VenueBinding,
)

MAX_RECEIPT_BYTES = 1024 * 1024
T = TypeVar("T")


def _scalar(value: object) -> object:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, frozenset):
        return sorted(value)
    if isinstance(value, Decimal):
        # Canonical coefficient/exponent spelling, without ambient-context rounding
        # or allocating exponent-sized fixed-point strings.
        sign, digits, exponent = value.as_tuple()
        if not isinstance(exponent, int):
            raise ValueError("nonfinite receipt decimal")
        digits = tuple(digits)
        end = len(digits)
        while end > 1 and digits[end - 1] == 0:
            end -= 1
        return str(Decimal((sign, digits[:end], exponent + len(digits) - end)))
    raise TypeError("unsupported receipt scalar")


def encode_market_receipt(candidate: MarketCandidate) -> bytes:
    instance(candidate, MarketCandidate, "candidate")
    canonical = replace(
        candidate,
        binding=replace(
            candidate.binding,
            venues=tuple(sorted(candidate.binding.venues, key=lambda v: v.provider_key)),
        ),
        selections=tuple(sorted(candidate.selections, key=lambda s: s.selection_id.value)),
        quotes=tuple(sorted(candidate.quotes, key=lambda q: q.quote_id.value)),
    )
    value = {
        "format": 1,
        "usage": "SYNTHETIC_ONLY",
        "parser_version": PARSER_VERSION,
        "normalizer_version": NORMALIZER_VERSION,
        "candidate": asdict(canonical),
    }
    body = json.dumps(
        value,
        default=_scalar,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    if len(body) > MAX_RECEIPT_BYTES:
        raise ValueError("market receipt exceeds size limit")
    return body


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate receipt field")
        result[key] = value
    return result


def _forbidden(value: str) -> Any:
    raise ValueError("receipt numbers must be integers or decimal strings")


def _record(
    cls: type[T], value: Any, converters: dict[str, Callable[[Any], Any]] | None = None
) -> T:
    if not isinstance(value, dict) or set(value) != {f.name for f in fields(cls)}:  # type: ignore[arg-type]
        raise ValueError("missing or unknown receipt fields")
    converted = dict(value)
    for key, convert in (converters or {}).items():
        converted[key] = convert(value[key])
    return cls(**converted)


def _id(cls: type[T]) -> Callable[[Any], T]:
    return lambda value: _record(cls, value)


def _time(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("receipt time must be text")
    return datetime.fromisoformat(value)


def _decimal(value: Any) -> Decimal:
    if not isinstance(value, str):
        raise ValueError("receipt odds must be decimal text")
    return Decimal(value)


def _many(convert: Callable[[Any], T]) -> Callable[[Any], tuple[T, ...]]:
    def decode(value: Any) -> tuple[T, ...]:
        if not isinstance(value, list):
            raise ValueError("receipt collection must be an array")
        return tuple(convert(item) for item in value)

    return decode


def _capabilities(value: Any) -> frozenset[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError("invalid capabilities")
    if len(set(value)) != len(value):
        raise ValueError("duplicate capabilities")
    return frozenset(value)


def _event_binding(value: Any) -> FixtureEventBinding:
    return _record(
        FixtureEventBinding,
        value,
        {
            "key": lambda v: _record(ProviderEntityKey, v, {"data_source_id": _id(DataSourceId)}),
            "event_id": _id(EventId),
            "sport": lambda v: _record(Sport, v, {"sport_id": _id(SportId)}),
            "competition": lambda v: _record(
                Competition, v, {"competition_id": _id(CompetitionId), "sport_id": _id(SportId)}
            ),
            "season": lambda v: _record(
                Season,
                v,
                {
                    "season_id": _id(SeasonId),
                    "competition_id": _id(CompetitionId),
                    "starts_at": _time,
                    "ends_at": _time,
                },
            ),
            "home": _participant,
            "away": _participant,
        },
    )


def _participant(value: Any) -> Participant:
    return _record(
        Participant, value, {"participant_id": _id(ParticipantId), "sport_id": _id(SportId)}
    )


def _binding(value: Any) -> MarketFixtureBinding:
    return _record(
        MarketFixtureBinding,
        value,
        {
            "event": _event_binding,
            "starts_at": _time,
            "source": lambda v: _record(
                DataSource,
                v,
                {
                    "data_source_id": _id(DataSourceId),
                    "source_type": SourceType,
                    "capabilities": _capabilities,
                },
            ),
            "venues": _many(
                lambda v: _record(
                    VenueBinding,
                    v,
                    {
                        "venue": lambda w: _record(
                            Venue,
                            w,
                            {
                                "venue_id": _id(VenueId),
                                "venue_type": VenueType,
                                "capabilities": _capabilities,
                            },
                        )
                    },
                )
            ),
        },
    )


def decode_market_receipt(body: bytes) -> MarketCandidate:
    instance(body, bytes, "body")
    if len(body) > MAX_RECEIPT_BYTES:
        raise ValueError("market receipt exceeds size limit")
    try:
        doc = json.loads(
            body, object_pairs_hook=_object, parse_float=_forbidden, parse_constant=_forbidden
        )
        if not isinstance(doc, dict) or set(doc) != {
            "format",
            "usage",
            "parser_version",
            "normalizer_version",
            "candidate",
        }:
            raise ValueError("invalid market receipt envelope")
        if (
            type(doc["format"]) is not int
            or doc["format"] != 1
            or doc["usage"] != "SYNTHETIC_ONLY"
            or doc["parser_version"] != PARSER_VERSION
            or doc["normalizer_version"] != NORMALIZER_VERSION
        ):
            raise ValueError("unsupported market receipt version/usage")
        result = _record(
            MarketCandidate,
            doc["candidate"],
            {
                "binding": _binding,
                "raw": lambda v: _record(
                    RawPayloadReference,
                    v,
                    {
                        "capture": lambda w: _record(
                            RawCapture,
                            w,
                            {
                                "data_source_id": _id(DataSourceId),
                                "ingested_at": _time,
                                "observed_at": _time,
                                "available_at": _time,
                                "effective_at": _time,
                            },
                        )
                    },
                ),
                "market": lambda v: _record(
                    Market,
                    v,
                    {"event_id": _id(EventId), "market_type": MarketType, "period": MarketPeriod},
                ),
                "selections": _many(
                    lambda v: _record(
                        Selection,
                        v,
                        {
                            "market_id": _id(MarketId),
                            "outcome": Outcome,
                            "participant_id": lambda w: (
                                None if w is None else _record(ParticipantId, w)
                            ),
                        },
                    )
                ),
                "quotes": _many(
                    lambda v: _record(
                        Quote,
                        v,
                        {
                            "quote_id": _id(QuoteId),
                            "selection_id": _id(SelectionId),
                            "data_source_id": _id(DataSourceId),
                            "venue_id": _id(VenueId),
                            "odds_decimal": _decimal,
                            "ingested_at": _time,
                            "observed_at": _time,
                            "available_at": _time,
                            "effective_at": _time,
                        },
                    )
                ),
            },
        )
        if encode_market_receipt(result) != body:
            raise ValueError("noncanonical market receipt")
        return result
    except (TypeError, KeyError, UnicodeError, RecursionError, ArithmeticError) as exc:
        raise ValueError("invalid market receipt") from exc
