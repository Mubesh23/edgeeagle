"""HTTP serialization over an inward-owned read port; no authoritative state."""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime
from typing import Annotated, cast

from fastapi import APIRouter, HTTPException, Path, Query, Request
from pydantic import AfterValidator, BaseModel
from sqlalchemy.exc import OperationalError, TimeoutError

from edgeeagle_domain._validation import text
from edgeeagle_domain.event_query import EventQuery, EventReader
from edgeeagle_domain.sports import CompetitionId, Event, EventId, SportId

EventReads = Callable[[], AbstractContextManager[EventReader]]


def canonical_text(value: str) -> str:
    text(value, "canonical value")
    if "\x00" in value:
        raise ValueError("NUL is not supported")
    return value


CanonicalText = Annotated[str, AfterValidator(canonical_text)]


class EventResponse(BaseModel):
    event_id: str
    sport_id: str
    competition_id: str
    season_id: str
    starts_at: datetime
    status: str
    venue_location: str | None

    @classmethod
    def from_event(cls, value: Event) -> "EventResponse":
        return cls(
            event_id=value.event_id.value,
            sport_id=value.sport_id.value,
            competition_id=value.competition_id.value,
            season_id=value.season_id.value,
            starts_at=value.starts_at,
            status=value.status,
            venue_location=value.venue_location,
        )


class EventEntryResponse(BaseModel):
    participant_id: str
    role: str


class EventDetailResponse(EventResponse):
    participants: list[EventEntryResponse]


class EventListResponse(BaseModel):
    items: list[EventResponse]
    next_after_event_id: str | None


class EventErrorResponse(BaseModel):
    detail: str


@contextmanager
def event_reader(request: Request) -> Iterator[EventReader]:
    factory = cast(EventReads | None, request.app.state.event_reads)
    if factory is None:
        raise HTTPException(503, "Event reads are not configured")
    try:
        with factory() as reader:
            yield reader
    except (OperationalError, TimeoutError) as error:
        raise HTTPException(503, "Event data is temporarily unavailable") from error


router = APIRouter()


@router.get(
    "/v1/events",
    response_model=EventListResponse,
    operation_id="list_events",
    responses={503: {"model": EventErrorResponse}},
)
def list_events(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    after_event_id: Annotated[CanonicalText | None, Query()] = None,
    sport_id: Annotated[CanonicalText | None, Query()] = None,
    competition_id: Annotated[CanonicalText | None, Query()] = None,
    status: Annotated[CanonicalText | None, Query()] = None,
) -> EventListResponse:
    query = EventQuery(
        limit=limit,
        after_event_id=EventId(after_event_id) if after_event_id is not None else None,
        sport_id=SportId(sport_id) if sport_id is not None else None,
        competition_id=CompetitionId(competition_id) if competition_id is not None else None,
        status=status,
    )
    with event_reader(request) as reader:
        page = reader.list_events(query)
        return EventListResponse(
            items=[EventResponse.from_event(e) for e in page.items],
            next_after_event_id=page.next_after_event_id.value
            if page.next_after_event_id
            else None,
        )


@router.get(
    "/v1/events/{eventId}",
    response_model=EventDetailResponse,
    operation_id="get_event",
    responses={404: {"model": EventErrorResponse}, 503: {"model": EventErrorResponse}},
)
def get_event(
    request: Request, event_id: Annotated[CanonicalText, Path(alias="eventId")]
) -> EventDetailResponse:
    identity = EventId(event_id)
    with event_reader(request) as reader:
        value = reader.get_event(identity)
        if value is None:
            raise HTTPException(404, "Event not found")
        return EventDetailResponse(
            **EventResponse.from_event(value).model_dump(),
            participants=[
                EventEntryResponse(participant_id=e.participant_id.value, role=e.role)
                for e in reader.get_event_participants(identity)
            ],
        )
