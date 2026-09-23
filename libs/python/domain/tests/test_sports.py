"""Structural sports records, independent of provider and sport-specific rules."""

from dataclasses import FrozenInstanceError, fields, replace
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pytest

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

SPORT = Sport(sport_id=SportId("s1"), code="SOCCER", name="Soccer")
COMPETITION = Competition(
    competition_id=CompetitionId("c1"),
    sport_id=SPORT.sport_id,
    name="Synthetic competition",
    country_or_region="International",
)
START = datetime(2026, 1, 1, tzinfo=UTC)
SEASON = Season(
    season_id=SeasonId("season1"),
    competition_id=COMPETITION.competition_id,
    name="2026",
    starts_at=START,
    ends_at=START + timedelta(days=365),
)
PARTICIPANT = Participant(
    participant_id=ParticipantId("p1"),
    sport_id=SPORT.sport_id,
    participant_type="TEAM",
    canonical_name="Synthetic team",
)
EVENT = Event(
    event_id=EventId("e1"),
    sport_id=SPORT.sport_id,
    competition_id=COMPETITION.competition_id,
    season_id=SEASON.season_id,
    starts_at=START,
    status="SCHEDULED",
)
ENTRY = EventParticipant(
    event_id=EVENT.event_id,
    participant_id=PARTICIPANT.participant_id,
    role="HOME",
)
RECORDS = [SPORT, COMPETITION, SEASON, PARTICIPANT, EVENT, ENTRY]
IDS = [SportId, CompetitionId, SeasonId, ParticipantId, EventId]


def test_hierarchy_references_are_explicit() -> None:
    assert COMPETITION.sport_id == SPORT.sport_id
    assert SEASON.competition_id == COMPETITION.competition_id
    assert EVENT.season_id == SEASON.season_id
    assert ENTRY.event_id == EVENT.event_id
    assert ENTRY.participant_id == PARTICIPANT.participant_id
    assert COMPETITION.gender_or_division is None
    assert EVENT.venue_location is None


def test_optional_metadata_and_unicode_names_are_preserved() -> None:
    assert replace(COMPETITION, gender_or_division="Women's").gender_or_division == "Women's"
    assert replace(EVENT, venue_location="São Paulo").venue_location == "São Paulo"
    assert replace(PARTICIPANT, canonical_name="Équipe A").canonical_name == "Équipe A"


@pytest.mark.parametrize("kind", ["TEAM", "PLAYER", "PAIR", "FIGHTER", "DRIVER"])
def test_participant_types_are_extensible(kind: str) -> None:
    assert replace(PARTICIPANT, participant_type=kind).participant_type == kind


def test_field_events_do_not_require_two_participants() -> None:
    entries = tuple(
        replace(ENTRY, participant_id=ParticipantId(f"p{i}"), role="FIELD") for i in range(12)
    )
    assert len({entry.participant_id for entry in entries}) == 12
    assert {entry.event_id for entry in entries} == {EVENT.event_id}


@pytest.mark.parametrize("record", RECORDS)
def test_records_are_immutable(record: Any) -> None:
    with pytest.raises(FrozenInstanceError):
        setattr(record, fields(record)[0].name, "changed")
    assert hash(record) == hash(replace(record))


def test_ids_are_distinct_and_immutable() -> None:
    assert len({identifier("same") for identifier in IDS}) == len(IDS)
    for identifier in IDS:
        assert identifier("same") == identifier("same")
        with pytest.raises(FrozenInstanceError):
            field = "value"
            setattr(identifier("same"), field, "changed")


@pytest.mark.parametrize("identifier", IDS)
@pytest.mark.parametrize(
    "value,error",
    [
        ("", ValueError),
        (" ", ValueError),
        (" padded", ValueError),
        (None, TypeError),
        (42, TypeError),
    ],
)
def test_invalid_ids(identifier: Any, value: Any, error: type[Exception]) -> None:
    with pytest.raises(error):
        identifier(value)


@pytest.mark.parametrize("record", RECORDS)
def test_id_fields_reject_other_id_types_and_strings(record: Any) -> None:
    for field in fields(record):
        if field.name.endswith("_id"):
            current = getattr(record, field.name)
            for wrong in ["raw-id", *(kind("wrong") for kind in IDS if kind is not type(current))]:
                with pytest.raises(TypeError, match=field.name):
                    replace(record, **{field.name: wrong})


@pytest.mark.parametrize(
    "record,field",
    [
        (SPORT, "code"),
        (SPORT, "name"),
        (COMPETITION, "name"),
        (COMPETITION, "country_or_region"),
        (COMPETITION, "gender_or_division"),
        (SEASON, "name"),
        (PARTICIPANT, "participant_type"),
        (PARTICIPANT, "canonical_name"),
        (EVENT, "status"),
        (EVENT, "venue_location"),
        (ENTRY, "role"),
    ],
)
@pytest.mark.parametrize(
    "value,error", [("", ValueError), (" ", ValueError), (" padded ", ValueError), (12, TypeError)]
)
def test_invalid_text(record: Any, field: str, value: Any, error: type[Exception]) -> None:
    with pytest.raises(error, match=field):
        replace(record, **{field: value})


@pytest.mark.parametrize(
    "record,field", [(SEASON, "starts_at"), (SEASON, "ends_at"), (EVENT, "starts_at")]
)
@pytest.mark.parametrize(
    "value,error",
    [(datetime(2026, 1, 1), ValueError), ("2026-01-01", TypeError), (None, TypeError)],
)
def test_schedule_requires_aware_datetimes(
    record: Any, field: str, value: Any, error: type[Exception]
) -> None:
    with pytest.raises(error, match=field):
        replace(record, **{field: value})


def test_offsets_are_preserved_and_season_order_compares_instants() -> None:
    offset_start = START.astimezone(timezone(timedelta(hours=3)))
    assert replace(EVENT, starts_at=offset_start).starts_at.utcoffset() == timedelta(hours=3)
    assert replace(SEASON, starts_at=offset_start, ends_at=START).ends_at == START
    with pytest.raises(ValueError, match="ends_at"):
        replace(SEASON, starts_at=offset_start, ends_at=START - timedelta(seconds=1))


def test_season_order_uses_instants_across_a_dst_fold() -> None:
    zone = ZoneInfo("America/New_York")
    earlier = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=0)
    later = earlier.replace(fold=1)
    assert replace(SEASON, starts_at=earlier, ends_at=later).ends_at.fold == 1
    with pytest.raises(ValueError, match="ends_at"):
        replace(SEASON, starts_at=later, ends_at=earlier)
