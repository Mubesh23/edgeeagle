from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from edgeeagle_api.main import create_app
from edgeeagle_domain.event_query import EventPage, EventReader
from edgeeagle_domain.sports import EventId
from tests.integration.test_sports_repository import ENTRIES, EVENT


def test_event_api_serialization_and_queries() -> None:
    reader = Mock(spec=EventReader)
    reader.get_event.return_value = EVENT
    reader.get_event_participants.return_value = ENTRIES
    reader.list_events.return_value = EventPage((EVENT,), EventId("e"))

    @contextmanager
    def reads() -> Iterator[EventReader]:
        yield reader

    with TestClient(create_app(event_reads=reads)) as client:
        response = client.get("/v1/events/e")
        assert response.status_code == 200
        assert response.json()["event_id"] == "e"
        assert len(response.json()["participants"]) == 12
        result = client.get(
            "/v1/events", params={"limit": 1, "sport_id": "s", "status": "SCHEDULED"}
        )
        assert result.status_code == 200
        assert result.json()["next_after_event_id"] == "e"
        assert reader.list_events.call_args.args[0].sport_id.value == "s"
        reader.get_event.return_value = None
        assert client.get("/v1/events/missing").status_code == 404
        reader.list_events.side_effect = OperationalError("secret-sql", {}, Exception("password"))
        unavailable = client.get("/v1/events")
        assert unavailable.status_code == 503
        assert "password" not in unavailable.text
        assert "secret-sql" not in unavailable.text


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=101",
        "limit=no",
        "sport_id=%20",
        "status=",
        "after_event_id=%20",
        "status=%00",
    ],
)
def test_event_api_invalid_queries(query: str) -> None:
    with TestClient(create_app()) as client:
        assert client.get("/v1/events?" + query).status_code == 422


def test_event_api_unconfigured_and_read_only() -> None:
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/v1/events").status_code == 503
        assert client.get("/v1/events/e").status_code == 503
        assert client.post("/v1/events").status_code == 405
        assert client.get("/v1/events/%20").status_code == 422
