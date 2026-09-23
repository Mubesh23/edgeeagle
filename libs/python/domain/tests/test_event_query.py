from datetime import datetime

import pytest

from edgeeagle_domain.event_query import EventQuery
from edgeeagle_domain.sports import EventId, SportId


@pytest.mark.parametrize("limit", [0, 101, True, 1.5])
def test_event_query_rejects_unbounded_limits(limit: int) -> None:
    with pytest.raises(ValueError):
        EventQuery(limit=limit)


def test_event_query_validates_filters() -> None:
    assert EventQuery().limit == 50
    assert EventQuery(limit=100, after_event_id=EventId("last"), sport_id=SportId("s"))
    with pytest.raises(ValueError):
        EventQuery(status=" ")
    with pytest.raises(TypeError):
        EventQuery(sport_id=datetime.now())  # type: ignore[arg-type]
