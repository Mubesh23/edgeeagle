from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import InternalError

from edgeeagle_api.local import create_local_app, event_transactions
from edgeeagle_api.main import create_app
from edgeeagle_domain.sports import EventId
from edgeeagle_persistence.sports import PostgresSportsRepository
from tests.integration.test_repositories import repository_engine as repository_engine
from tests.integration.test_sports_repository import ENTRIES, EVENT, seed


def test_event_api_committed_visibility_and_pagination(
    repository_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(
        "EDGEEAGLE_DATABASE_URL", repository_engine.url.render_as_string(hide_password=False)
    )
    with TestClient(create_local_app()) as client:
        assert client.get("/v1/events").json() == {"items": [], "next_after_event_id": None}
        with repository_engine.begin() as connection:
            writer = PostgresSportsRepository(connection)
            seed(writer)
            writer.add_event(EVENT, ENTRIES)
            assert client.get("/v1/events/e").status_code == 404
        detail = client.get("/v1/events/e")
        assert detail.status_code == 200
        assert len(detail.json()["participants"]) == 12
        assert detail.json()["season_id"] == EVENT.season_id.value
        assert detail.json()["venue_location"] is None
        with repository_engine.connect() as connection:
            transaction = connection.begin()
            writer = PostgresSportsRepository(connection)
            changed = replace(EVENT, event_id=EventId("z"))
            writer.add_event(changed, tuple(replace(e, event_id=changed.event_id) for e in ENTRIES))
            transaction.rollback()
        assert client.get("/v1/events/z").status_code == 404
        page = client.get("/v1/events?limit=1&sport_id=s&competition_id=c&status=SCHEDULED").json()
        assert [e["event_id"] for e in page["items"]] == ["e"]
        assert page["next_after_event_id"] is None
        assert client.get("/v1/events?after_event_id=e").json()["items"] == []


def test_event_api_transaction_is_read_only_snapshot(repository_engine: Engine) -> None:
    with repository_engine.begin() as connection:
        writer = PostgresSportsRepository(connection)
        seed(writer)
        writer.add_event(EVENT, ENTRIES)
    with event_transactions(repository_engine)() as reader:
        assert reader.get_event(EVENT.event_id) == EVENT
        with repository_engine.begin() as other:
            other.execute(text("UPDATE events SET status = 'CHANGED' WHERE event_id = 'e'"))
        assert reader.get_event(EVENT.event_id) == EVENT
    with event_transactions(repository_engine)() as reader:
        value = reader.get_event(EVENT.event_id)
        assert value is not None and value.status == "CHANGED"
    with pytest.raises(InternalError, match="read-only"):
        with event_transactions(repository_engine)() as reader:
            # Verify the actual request connection, not a separately configured engine.
            reader._connection.execute(text("UPDATE events SET status = 'BAD'"))  # type: ignore[attr-defined]


def test_event_api_missing_schema_is_not_an_empty_success(repository_engine: Engine) -> None:
    with repository_engine.begin() as connection:
        connection.execute(text("ALTER TABLE events RENAME TO temporarily_missing_events"))
    with TestClient(
        create_app(event_reads=event_transactions(repository_engine)), raise_server_exceptions=False
    ) as client:
        response = client.get("/v1/events")
        assert response.status_code == 500
        assert "SELECT" not in response.text
