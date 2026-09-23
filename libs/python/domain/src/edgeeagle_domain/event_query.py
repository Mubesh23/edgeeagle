"""Bounded current-state reads; never a historical research snapshot."""

from dataclasses import dataclass
from typing import Protocol

from edgeeagle_domain._validation import instance, text
from edgeeagle_domain.sports import CompetitionId, Event, EventId, EventParticipant, SportId


@dataclass(frozen=True, kw_only=True)
class EventQuery:
    limit: int = 50
    after_event_id: EventId | None = None
    sport_id: SportId | None = None
    competition_id: CompetitionId | None = None
    status: str | None = None

    def __post_init__(self) -> None:
        if type(self.limit) is not int or not 1 <= self.limit <= 100:
            raise ValueError("limit must be an integer in [1, 100]")
        for value, kind, field in (
            (self.after_event_id, EventId, "after_event_id"),
            (self.sport_id, SportId, "sport_id"),
            (self.competition_id, CompetitionId, "competition_id"),
        ):
            if value is not None:
                instance(value, kind, field)
        if self.status is not None:
            text(self.status, "status")


@dataclass(frozen=True)
class EventPage:
    items: tuple[Event, ...]
    next_after_event_id: EventId | None


class EventReader(Protocol):
    """Caller-owned transaction. Lists sort by ID, with an exclusive continuation."""

    def list_events(self, query: EventQuery) -> EventPage: ...

    def get_event(self, event_id: EventId) -> Event | None: ...

    def get_event_participants(self, event_id: EventId) -> tuple[EventParticipant, ...]: ...
