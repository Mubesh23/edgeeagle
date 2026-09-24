"""Bounded Sportmonks v3 scheduled-fixture staging, not canonical normalization."""

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, NoReturn

from edgeeagle_domain._validation import aware_datetime

PARSER_VERSION = "sportmonks-scheduled-fixture-json-v1"
MAX_BYTES = 1024 * 1024


@dataclass(frozen=True)
class NativeSportmonksParticipant:
    participant_id: int
    name: str


@dataclass(frozen=True)
class NativeSportmonksFixture:
    fixture_id: int
    sport_id: int
    league_id: int
    season_id: int
    state_id: int
    starts_at: datetime
    home: NativeSportmonksParticipant
    away: NativeSportmonksParticipant


def _object(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("expected Sportmonks object")
    return value


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _constant(value: str) -> NoReturn:
    raise ValueError("nonstandard JSON number")


def _native_id(value: object) -> int:
    if type(value) is not int or not 0 < value <= 2**63 - 1:
        raise ValueError("expected positive bounded integer native ID")
    return value


def _name(value: object) -> str:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 256
        or value != value.strip()
        or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value)
    ):
        raise ValueError("invalid Sportmonks participant name")
    return value


def _kickoff(row: dict[str, Any]) -> datetime:
    stamp = row["starting_at_timestamp"]
    if type(stamp) is not int:
        raise ValueError("expected integral Unix-second kickoff")
    value = row["starting_at"]
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}", value
    ):
        raise ValueError("expected UTC kickoff text")
    result = datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    if result != datetime.fromtimestamp(stamp, UTC):
        raise ValueError("Sportmonks kickoff representations disagree")
    return result


def parse_scheduled_fixture(
    body: bytes, *, expected_fixture_id: int, snapshot_at: datetime
) -> NativeSportmonksFixture:
    """Parse one declared UTC/NS response, with no I/O, mappings or clock reads.

    Production callers must first retain/verify raw bytes. snapshot_at is explicit
    capture or simulated fixture context, not historical availability evidence.
    Unknown additive fields stay raw-only; native staging never becomes a feature
    or canonical event merely because it parsed successfully.
    """
    if not isinstance(body, bytes) or len(body) > MAX_BYTES:
        raise ValueError("Sportmonks body must be bounded bytes")
    _native_id(expected_fixture_id)
    aware_datetime(snapshot_at, "snapshot_at")
    try:
        envelope = _object(
            json.loads(
                body.decode("utf-8"),
                object_pairs_hook=_pairs,
                parse_float=Decimal,
                parse_constant=_constant,
            )
        )
        if any(key in envelope for key in ("error", "errors", "message")):
            raise ValueError("Sportmonks error envelope")
        if envelope["timezone"] != "UTC":
            raise ValueError("require explicit UTC response timezone")
        row = _object(envelope["data"])
        identity = _native_id(row["id"])
        if identity != expected_fixture_id:
            raise ValueError("unexpected Sportmonks fixture ID")
        if _native_id(row["sport_id"]) != 1 or row["placeholder"] is not False:
            raise ValueError("require a non-placeholder soccer fixture")
        state = _object(row["state"])
        if (
            _native_id(row["state_id"]) != 1
            or _native_id(state["id"]) != 1
            or state["state"] != "NS"
        ):
            raise ValueError("only scheduled NS fixtures are supported")
        kickoff = _kickoff(row)
        if kickoff <= snapshot_at.astimezone(UTC):
            raise ValueError("snapshot must precede scheduled kickoff")
        native = row["participants"]
        if not isinstance(native, list) or len(native) != 2:
            raise ValueError("require exactly two participants")
        participants: dict[str, NativeSportmonksParticipant] = {}
        for item in native:
            participant = _object(item)
            if _native_id(participant["sport_id"]) != 1 or participant["placeholder"] is not False:
                raise ValueError("require non-placeholder soccer participants")
            role = _object(participant["meta"])["location"]
            if not isinstance(role, str) or role not in ("home", "away") or role in participants:
                raise ValueError("require distinct home/away roles")
            participants[role] = NativeSportmonksParticipant(
                _native_id(participant["id"]), _name(participant["name"])
            )
        home, away = participants["home"], participants["away"]
        if home.participant_id == away.participant_id:
            raise ValueError("duplicate Sportmonks participant identity")
        return NativeSportmonksFixture(
            identity,
            1,
            _native_id(row["league_id"]),
            _native_id(row["season_id"]),
            1,
            kickoff,
            home,
            away,
        )
    except (KeyError, TypeError, UnicodeError, RecursionError, ArithmeticError, OSError) as exc:
        raise ValueError("malformed Sportmonks fixture response") from exc
