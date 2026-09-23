"""Wrong record/identity types must fail without executing SQL."""

from datetime import UTC, datetime
from unittest.mock import create_autospec

import pytest
from sqlalchemy import Connection

from edgeeagle_domain.sports import CompetitionId, Event, EventId, SeasonId, SportId
from edgeeagle_persistence.sports import PostgresSportsRepository


@pytest.mark.parametrize(
    "method",
    [
        "add_sport",
        "add_competition",
        "add_season",
        "add_participant",
        "get_sport",
        "get_competition",
        "get_season",
        "get_participant",
        "get_event",
        "get_event_participants",
    ],
)
def test_sports_repository_wrong_types_do_not_execute_sql(method: str) -> None:
    connection = create_autospec(Connection, instance=True)
    repository = PostgresSportsRepository(connection)
    with pytest.raises(TypeError):
        getattr(repository, method)(object())
    connection.execute.assert_not_called()


def test_sports_repository_rejects_invalid_event_inputs_without_sql() -> None:
    connection = create_autospec(Connection, instance=True)
    repository = PostgresSportsRepository(connection)
    event = Event(
        event_id=EventId("e"),
        sport_id=SportId("s"),
        competition_id=CompetitionId("c"),
        season_id=SeasonId("season"),
        starts_at=datetime(2026, 1, 1, tzinfo=UTC),
        status="SCHEDULED",
    )
    with pytest.raises(TypeError, match="Event"):
        repository.add_event(object(), ())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="tuple"):
        repository.add_event(event, [])  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="EventParticipant"):
        repository.add_event(event, (object(),))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="SportId"):
        repository.get_sport(EventId("s"))  # type: ignore[arg-type]
    connection.execute.assert_not_called()
