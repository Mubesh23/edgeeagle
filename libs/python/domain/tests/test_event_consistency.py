"""Cross-record checks use supplied records only, never external lookups."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from edgeeagle_domain.consistency import validate_event_context
from edgeeagle_domain.sports import (
    Competition,
    CompetitionId,
    Event,
    EventId,
    EventParticipant,
    Participant,
    ParticipantId,
    Season,
    SeasonId,
    Sport,
    SportId,
)


@pytest.fixture
def context() -> dict[str, Any]:
    sport = Sport(sport_id=SportId("sport"), code="SOCCER", name="Soccer")
    competition = Competition(
        competition_id=CompetitionId("competition"),
        sport_id=sport.sport_id,
        name="Fixture league",
        country_or_region="International",
    )
    start = datetime(2026, 1, 1, tzinfo=UTC)
    season = Season(
        season_id=SeasonId("season"),
        competition_id=competition.competition_id,
        name="2026",
        starts_at=start,
        ends_at=start + timedelta(days=365),
    )
    event = Event(
        event_id=EventId("event"),
        sport_id=sport.sport_id,
        competition_id=competition.competition_id,
        season_id=season.season_id,
        starts_at=start,
        status="SCHEDULED",
    )
    participants = tuple(
        Participant(
            participant_id=ParticipantId(str(i)),
            sport_id=sport.sport_id,
            participant_type="TEAM",
            canonical_name=f"Fixture {i}",
        )
        for i in range(2)
    )
    entries = tuple(
        EventParticipant(event_id=event.event_id, participant_id=p.participant_id, role="FIELD")
        for p in participants
    )
    return dict(
        sport=sport,
        competition=competition,
        season=season,
        event=event,
        participants=participants,
        entries=entries,
    )


def test_valid_context_is_deterministic_and_unchanged(context: dict[str, Any]) -> None:
    before = context.copy()
    validate_event_context(**context)
    validate_event_context(**context)
    assert context == before


@pytest.mark.parametrize(
    "record,field,value",
    [
        ("event", "sport_id", SportId("other")),
        ("competition", "sport_id", SportId("other")),
        ("event", "competition_id", CompetitionId("other")),
        ("season", "competition_id", CompetitionId("other")),
        ("event", "season_id", SeasonId("other")),
    ],
)
def test_rejects_mismatched_hierarchy(
    context: dict[str, Any], record: str, field: str, value: Any
) -> None:
    context[record] = replace(context[record], **{field: value})
    with pytest.raises(ValueError, match=field):
        validate_event_context(**context)


def test_rejects_participant_from_another_sport(context: dict[str, Any]) -> None:
    context["participants"] = (replace(context["participants"][0], sport_id=SportId("other")),)
    with pytest.raises(ValueError, match="sport_id"):
        validate_event_context(**context)


def test_rejects_entry_from_another_event(context: dict[str, Any]) -> None:
    context["entries"] = (replace(context["entries"][0], event_id=EventId("other")),)
    with pytest.raises(ValueError, match="event_id"):
        validate_event_context(**context)


def test_rejects_missing_referenced_participant(context: dict[str, Any]) -> None:
    context["participants"] = context["participants"][:1]
    with pytest.raises(ValueError, match="missing participant"):
        validate_event_context(**context)


@pytest.mark.parametrize("different_role", [False, True])
def test_rejects_duplicate_entries(context: dict[str, Any], different_role: bool) -> None:
    entry = context["entries"][0]
    context["entries"] += (replace(entry, role="AWAY") if different_role else entry,)
    with pytest.raises(ValueError, match="duplicate entry"):
        validate_event_context(**context)


@pytest.mark.parametrize("conflicting", [False, True])
def test_rejects_duplicate_participant_records(context: dict[str, Any], conflicting: bool) -> None:
    participant = context["participants"][0]
    context["participants"] += (
        replace(participant, canonical_name="Conflicting") if conflicting else participant,
    )
    with pytest.raises(ValueError, match="duplicate participant"):
        validate_event_context(**context)


def test_rejects_unattached_participants(context: dict[str, Any]) -> None:
    context["entries"] = context["entries"][:1]
    with pytest.raises(ValueError, match="unattached participant"):
        validate_event_context(**context)


def test_rejects_empty_event_context(context: dict[str, Any]) -> None:
    context.update(entries=(), participants=())
    with pytest.raises(ValueError, match="at least one entry"):
        validate_event_context(**context)


@pytest.mark.parametrize("count", [1, 2, 12])
def test_no_two_team_or_unique_role_assumption(context: dict[str, Any], count: int) -> None:
    context["participants"] = tuple(
        replace(
            context["participants"][0],
            participant_id=ParticipantId(str(i)),
            participant_type="PLAYER",
        )
        for i in range(count)
    )
    context["entries"] = tuple(
        replace(context["entries"][0], participant_id=p.participant_id)
        for p in context["participants"]
    )
    validate_event_context(**context)
    context["participants"] = tuple(reversed(context["participants"]))
    context["entries"] = tuple(reversed(context["entries"]))
    validate_event_context(**context)


def test_does_not_invent_season_date_or_lifecycle_policy(context: dict[str, Any]) -> None:
    context["event"] = replace(
        context["event"],
        starts_at=context["season"].ends_at + timedelta(days=7),
        status="RESCHEDULED",
    )
    validate_event_context(**context)


@pytest.mark.parametrize(
    "field", ["sport", "competition", "season", "event", "participants", "entries"]
)
def test_rejects_wrong_argument_types(context: dict[str, Any], field: str) -> None:
    context[field] = None
    with pytest.raises(TypeError, match=field):
        validate_event_context(**context)


@pytest.mark.parametrize("field", ["participants", "entries"])
def test_rejects_wrong_collection_members(context: dict[str, Any], field: str) -> None:
    context[field] = (None,)
    with pytest.raises(TypeError, match=field):
        validate_event_context(**context)
