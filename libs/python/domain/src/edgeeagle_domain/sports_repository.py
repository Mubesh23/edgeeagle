"""Ports for current sports reference records and atomic event/entry insertion."""

from typing import Protocol

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


class SportsRepository(Protocol):
    """Insert-only current state. Existing IDs raise DuplicateRecordError.

    Callers own transactions. Event references must already exist. Reads return
    None for absent records; entry reads return an empty tuple for absent/empty
    events and are ordered by opaque participant ID (not sporting rank).
    """

    def add_sport(self, sport: Sport) -> None: ...

    def get_sport(self, sport_id: SportId) -> Sport | None: ...

    def add_competition(self, competition: Competition) -> None: ...

    def get_competition(self, competition_id: CompetitionId) -> Competition | None: ...

    def add_season(self, season: Season) -> None: ...

    def get_season(self, season_id: SeasonId) -> Season | None: ...

    def add_participant(self, participant: Participant) -> None: ...

    def get_participant(self, participant_id: ParticipantId) -> Participant | None: ...

    def add_event(self, event: Event, entries: tuple[EventParticipant, ...]) -> None: ...

    def get_event(self, event_id: EventId) -> Event | None: ...

    def get_event_participants(self, event_id: EventId) -> tuple[EventParticipant, ...]: ...
