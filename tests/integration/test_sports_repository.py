"""Canonical sports persistence through real PostgreSQL transactions."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from edgeeagle_domain.repositories import DuplicateRecordError
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
from edgeeagle_domain.sports_repository import SportsRepository
from edgeeagle_persistence.sports import PostgresSportsRepository
from tests.integration.test_repositories import repository_engine as repository_engine

SPORT = Sport(sport_id=SportId("s"), code="SYNTHETIC", name="Fixture sport")
COMPETITION = Competition(
    competition_id=CompetitionId("c"),
    sport_id=SPORT.sport_id,
    name="Fixture'; --",
    country_or_region="synthetic",
)
START = datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=3)))
SEASON = Season(
    season_id=SeasonId("season"),
    competition_id=COMPETITION.competition_id,
    name="Fixture season",
    starts_at=START,
    ends_at=START,
)
EVENT = Event(
    event_id=EventId("e"),
    sport_id=SPORT.sport_id,
    competition_id=COMPETITION.competition_id,
    season_id=SEASON.season_id,
    starts_at=START + timedelta(days=1),
    status="SCHEDULED",
)
PARTICIPANTS = tuple(
    Participant(
        participant_id=ParticipantId(f"p{i:02}"),
        sport_id=SPORT.sport_id,
        participant_type="PLAYER",
        canonical_name=f"Player {i}",
    )
    for i in range(12)
)
ENTRIES = tuple(
    EventParticipant(event_id=EVENT.event_id, participant_id=p.participant_id, role="FIELD")
    for p in PARTICIPANTS
)


def seed(repository: SportsRepository) -> None:
    repository.add_sport(SPORT)
    repository.add_competition(COMPETITION)
    repository.add_season(SEASON)
    for participant in PARTICIPANTS:
        repository.add_participant(participant)


def test_sports_repository_roundtrip_commit_and_duplicate(repository_engine: Engine) -> None:
    with repository_engine.begin() as connection:
        repository: SportsRepository = PostgresSportsRepository(connection)
        assert repository.get_sport(SPORT.sport_id) is None
        assert repository.get_competition(COMPETITION.competition_id) is None
        assert repository.get_season(SEASON.season_id) is None
        assert repository.get_participant(PARTICIPANTS[0].participant_id) is None
        assert repository.get_event(EVENT.event_id) is None
        assert repository.get_event_participants(EVENT.event_id) == ()
        seed(repository)
        repository.add_event(EVENT, tuple(reversed(ENTRIES)))
        duplicate_operations: tuple[Callable[[], None], ...] = (
            lambda: repository.add_sport(SPORT),
            lambda: repository.add_competition(COMPETITION),
            lambda: repository.add_season(SEASON),
            lambda: repository.add_participant(PARTICIPANTS[0]),
            lambda: repository.add_event(EVENT, ENTRIES),
        )
        for operation in duplicate_operations:
            with pytest.raises(DuplicateRecordError):
                operation()
        with repository_engine.begin() as other:
            assert PostgresSportsRepository(other).get_event(EVENT.event_id) is None
    with repository_engine.begin() as connection:
        repository = PostgresSportsRepository(connection)
        assert repository.get_sport(SPORT.sport_id) == SPORT
        assert repository.get_competition(COMPETITION.competition_id) == COMPETITION
        assert repository.get_season(SEASON.season_id) == SEASON
        assert repository.get_participant(PARTICIPANTS[0].participant_id) == PARTICIPANTS[0]
        result = repository.get_event(EVENT.event_id)
        assert result == EVENT
        assert result.starts_at.astimezone(UTC) == EVENT.starts_at.astimezone(UTC)
        assert repository.get_event_participants(EVENT.event_id) == ENTRIES
        assert connection.scalars(
            text("SELECT DISTINCT sport_id FROM event_participants")
        ).all() == ["s"]


def test_sports_repository_rollback(repository_engine: Engine) -> None:
    with pytest.raises(RuntimeError, match="abort"), repository_engine.begin() as connection:
        repository = PostgresSportsRepository(connection)
        seed(repository)
        repository.add_event(EVENT, ENTRIES)
        raise RuntimeError("abort")
    with repository_engine.begin() as connection:
        repository = PostgresSportsRepository(connection)
        assert repository.get_sport(SPORT.sport_id) is None
        assert repository.get_event(EVENT.event_id) is None
        assert repository.get_event_participants(EVENT.event_id) == ()


def test_sports_repository_child_failure_is_atomic(repository_engine: Engine) -> None:
    with repository_engine.begin() as connection:
        repository = PostgresSportsRepository(connection)
        seed(repository)
        connection.execute(
            text("ALTER TABLE event_participants ADD CHECK (participant_id <> 'p11')")
        )
        with pytest.raises(IntegrityError):
            repository.add_event(EVENT, ENTRIES)
        assert repository.get_event(EVENT.event_id) is None
        assert repository.get_event_participants(EVENT.event_id) == ()
        assert repository.get_sport(SPORT.sport_id) == SPORT
        repository.add_event(EVENT, ENTRIES[:1])
    with repository_engine.begin() as connection:
        assert (
            PostgresSportsRepository(connection).get_event_participants(EVENT.event_id)
            == ENTRIES[:1]
        )


def test_sports_repository_optional_fields_and_reference_failures(
    repository_engine: Engine,
) -> None:
    with repository_engine.begin() as connection:
        repository = PostgresSportsRepository(connection)
        with pytest.raises(IntegrityError):
            repository.add_competition(COMPETITION)
        with pytest.raises(IntegrityError):
            repository.add_season(SEASON)
        with pytest.raises(IntegrityError):
            repository.add_participant(PARTICIPANTS[0])
        repository.add_sport(SPORT)
        competition = replace(COMPETITION, gender_or_division="OPEN")
        repository.add_competition(competition)
        repository.add_season(SEASON)
        repository.add_participant(PARTICIPANTS[0])
        event = replace(EVENT, venue_location="Fixture ground")
        repository.add_event(event, ENTRIES[:1])
        assert repository.get_competition(competition.competition_id) == competition
        assert repository.get_event(event.event_id) == event


def test_sports_repository_requires_transaction(repository_engine: Engine) -> None:
    with repository_engine.connect() as connection:
        repository = PostgresSportsRepository(connection)
        with pytest.raises(RuntimeError, match="active caller-owned"):
            repository.add_sport(SPORT)
        with pytest.raises(RuntimeError, match="active caller-owned"):
            repository.get_event(EVENT.event_id)
        with pytest.raises(RuntimeError, match="active caller-owned"):
            repository.get_event_participants(EVENT.event_id)
        connection.execution_options(isolation_level="AUTOCOMMIT")
        with connection.begin(), pytest.raises(RuntimeError, match="Autocommit"):
            repository.add_event(EVENT, ENTRIES)


@pytest.mark.parametrize(
    "case",
    [
        "empty",
        "duplicate",
        "wrong_event",
        "missing_participant",
        "missing_sport",
        "missing_competition",
        "missing_season",
        "wrong_sport",
        "wrong_season",
        "wrong_participant_sport",
    ],
)
def test_sports_repository_rejects_inconsistent_context(
    repository_engine: Engine, case: str
) -> None:
    with repository_engine.begin() as connection:
        repository = PostgresSportsRepository(connection)
        seed(repository)
        event, entries = EVENT, ENTRIES
        if case == "empty":
            entries = ()
        elif case == "duplicate":
            entries = ENTRIES + ENTRIES[:1]
        elif case == "wrong_event":
            entries = (replace(ENTRIES[0], event_id=EventId("other")),)
        elif case == "missing_participant":
            entries = (replace(ENTRIES[0], participant_id=ParticipantId("missing")),)
        elif case == "missing_sport":
            event = replace(EVENT, sport_id=SportId("missing"))
        elif case == "missing_competition":
            event = replace(EVENT, competition_id=CompetitionId("missing"))
        elif case == "missing_season":
            event = replace(EVENT, season_id=SeasonId("missing"))
        elif case == "wrong_sport":
            repository.add_sport(replace(SPORT, sport_id=SportId("other")))
            event = replace(EVENT, sport_id=SportId("other"))
        elif case == "wrong_season":
            repository.add_competition(replace(COMPETITION, competition_id=CompetitionId("other")))
            repository.add_season(
                replace(SEASON, season_id=SeasonId("other"), competition_id=CompetitionId("other"))
            )
            event = replace(EVENT, season_id=SeasonId("other"))
        else:
            repository.add_sport(replace(SPORT, sport_id=SportId("other")))
            repository.add_participant(
                replace(
                    PARTICIPANTS[0],
                    participant_id=ParticipantId("other"),
                    sport_id=SportId("other"),
                )
            )
            entries = (replace(ENTRIES[0], participant_id=ParticipantId("other")),)
        with pytest.raises(ValueError):
            repository.add_event(event, entries)
        assert repository.get_event(EVENT.event_id) is None
        assert repository.get_event_participants(EVENT.event_id) == ()
