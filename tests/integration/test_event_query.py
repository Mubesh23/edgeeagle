from dataclasses import replace

import pytest
from sqlalchemy import Engine

from edgeeagle_domain.event_query import EventQuery, EventReader
from edgeeagle_domain.sports import CompetitionId, EventId, SportId
from edgeeagle_persistence.event_query import PostgresEventReader
from edgeeagle_persistence.sports import PostgresSportsRepository
from tests.integration.test_repositories import repository_engine as repository_engine
from tests.integration.test_sports_repository import ENTRIES, EVENT, seed


def test_event_query_pages_filters_and_detail(repository_engine: Engine) -> None:
    with repository_engine.begin() as connection:
        writer = PostgresSportsRepository(connection)
        seed(writer)
        for key in ("z", "A", "a"):
            value = replace(EVENT, event_id=EventId(key))
            writer.add_event(value, tuple(replace(e, event_id=value.event_id) for e in ENTRIES))
    with repository_engine.begin() as connection:
        reader: EventReader = PostgresEventReader(connection)
        page = reader.list_events(EventQuery(limit=2))
        assert [e.event_id.value for e in page.items] == ["A", "a"]
        assert page.next_after_event_id == EventId("a")
        end = reader.list_events(EventQuery(limit=2, after_event_id=page.next_after_event_id))
        assert [e.event_id.value for e in end.items] == ["z"]
        assert end.next_after_event_id is None
        assert len(reader.list_events(EventQuery(sport_id=SportId("s"))).items) == 3
        assert len(reader.list_events(EventQuery(competition_id=CompetitionId("c"))).items) == 3
        assert len(reader.list_events(EventQuery(status="SCHEDULED")).items) == 3
        for query in (
            EventQuery(sport_id=SportId("missing")),
            EventQuery(competition_id=CompetitionId("missing")),
            EventQuery(status="SCHEDULED' OR TRUE --"),
            EventQuery(after_event_id=EventId("zz")),
        ):
            assert reader.list_events(query).items == ()
        assert reader.get_event(EventId("a")) == replace(EVENT, event_id=EventId("a"))
        assert len(reader.get_event_participants(EventId("a"))) == 12
        assert reader.get_event(EventId("missing")) is None


def test_event_query_requires_transaction(repository_engine: Engine) -> None:
    with repository_engine.connect() as connection:
        with pytest.raises(RuntimeError, match="active caller-owned"):
            PostgresEventReader(connection).list_events(EventQuery())
