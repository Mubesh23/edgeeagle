"""Fixture-only event adapter; not a live Odds API schema or identity resolver."""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import NoReturn

from edgeeagle_domain.consistency import validate_event_context
from edgeeagle_domain.mappings import ProviderEntityKey
from edgeeagle_domain.raw import RawPayloadIntegrityError, RawPayloadReference, RawPayloadStore
from edgeeagle_domain.sports import (
    Competition,
    Event,
    EventId,
    EventParticipant,
    Participant,
    Season,
    Sport,
)
from edgeeagle_ingestion.events import EventCandidate


def _text(value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("fixture fields must be nonblank unpadded strings")
    return value


@dataclass(frozen=True, kw_only=True)
class FixtureEventBinding:
    key: ProviderEntityKey
    competition_key: str
    home_label: str
    away_label: str
    event_id: EventId
    sport: Sport
    competition: Competition
    season: Season
    home: Participant
    away: Participant
    status: str
    context_version: str

    def __post_init__(self) -> None:
        for name, expected in (
            ("key", ProviderEntityKey),
            ("event_id", EventId),
            ("sport", Sport),
            ("competition", Competition),
            ("season", Season),
            ("home", Participant),
            ("away", Participant),
        ):
            if not isinstance(getattr(self, name), expected):
                raise TypeError(f"invalid binding {name}")
        for name in ("competition_key", "home_label", "away_label", "status", "context_version"):
            _text(getattr(self, name))
        if self.key.provider_entity_type != "event":
            raise ValueError("binding key must identify an event")


@dataclass(frozen=True)
class _StagedEvent:
    provider_id: str
    competition_key: str
    starts_at: datetime
    home_label: str
    away_label: str


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _constant(value: str) -> NoReturn:
    raise ValueError("nonstandard JSON numeric constant")


def _parse(body: bytes) -> tuple[_StagedEvent, ...]:
    rows = json.loads(body.decode("utf-8"), object_pairs_hook=_object, parse_constant=_constant)
    if not isinstance(rows, list):
        raise ValueError("fixture must contain an event array")
    result: list[_StagedEvent] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("fixture event must be an object")
        provider_id = _text(row.get("id"))
        competition = _text(row.get("sport_key"))
        home, away = _text(row.get("home_team")), _text(row.get("away_team"))
        starts_at = datetime.fromisoformat(_text(row.get("commence_time")))
        if starts_at.utcoffset() is None:
            raise ValueError("fixture start must be timezone-aware")
        if provider_id in seen or home == away:
            raise ValueError("duplicate event or ambiguous participant labels")
        seen.add(provider_id)
        result.append(_StagedEvent(provider_id, competition, starts_at.astimezone(UTC), home, away))
    return tuple(result)


def normalize_fixture_events(
    store: RawPayloadStore,
    reference: RawPayloadReference,
    bindings: tuple[FixtureEventBinding, ...],
) -> tuple[EventCandidate, ...]:
    """Read retained bytes and produce a complete candidate batch, with no writes."""
    if not isinstance(reference, RawPayloadReference):
        raise TypeError("reference must be a RawPayloadReference")
    if not isinstance(bindings, tuple) or any(
        not isinstance(b, FixtureEventBinding) for b in bindings
    ):
        raise TypeError("bindings must be a tuple of FixtureEventBinding")
    body = store.get(reference)
    if body is None:
        raise FileNotFoundError("retained raw fixture is missing")
    if len(body) != reference.size_bytes or hashlib.sha256(body).hexdigest() != reference.sha256:
        raise RawPayloadIntegrityError("retained raw fixture does not match reference")
    rows = _parse(body)
    by_id = {b.key.provider_entity_id: b for b in bindings}
    if (
        len(by_id) != len(bindings)
        or len({b.event_id for b in bindings}) != len(bindings)
        or set(by_id) != {row.provider_id for row in rows}
    ):
        raise ValueError("bindings must cover each event exactly once without identity collapse")
    results: list[EventCandidate] = []
    for row in rows:
        binding = by_id[row.provider_id]
        if binding.key.data_source_id != reference.capture.data_source_id or (
            binding.competition_key,
            binding.home_label,
            binding.away_label,
        ) != (row.competition_key, row.home_label, row.away_label):
            raise ValueError("fixture and explicit binding do not match")
        event = Event(
            event_id=binding.event_id,
            sport_id=binding.sport.sport_id,
            competition_id=binding.competition.competition_id,
            season_id=binding.season.season_id,
            starts_at=row.starts_at,
            status=binding.status,
        )
        entries = (
            EventParticipant(
                event_id=event.event_id, participant_id=binding.home.participant_id, role="HOME"
            ),
            EventParticipant(
                event_id=event.event_id, participant_id=binding.away.participant_id, role="AWAY"
            ),
        )
        validate_event_context(
            event=event,
            sport=binding.sport,
            competition=binding.competition,
            season=binding.season,
            participants=(binding.home, binding.away),
            entries=entries,
        )
        results.append(
            EventCandidate(
                event=event,
                entries=entries,
                raw=reference,
                provider_key=binding.key,
                parser_version="synthetic-odds-events-v1",
                normalizer_version="synthetic-event-bindings-v1",
                context_version=binding.context_version,
            )
        )
    return tuple(results)
