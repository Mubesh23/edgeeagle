"""Deterministic relationship checks over an explicitly supplied event context."""

from collections.abc import Sequence

from edgeeagle_domain._validation import instance
from edgeeagle_domain.sports import (
    Competition,
    Event,
    EventParticipant,
    Participant,
    ParticipantId,
    Season,
    Sport,
)


def validate_event_context(
    *,
    event: Event,
    sport: Sport,
    competition: Competition,
    season: Season,
    participants: Sequence[Participant],
    entries: Sequence[EventParticipant],
) -> None:
    """Reject inconsistent resolved records without fetching, mutating, or repairing them.

    Participants must be exactly those attached to this event, not a global catalog.
    Require at least one entry, but leave sport-specific cardinality/role rules to
    later validators. Success proves local consistency, not persisted existence,
    roster completeness, lifecycle validity, or historical availability.
    """
    instance(event, Event, "event")
    instance(sport, Sport, "sport")
    instance(competition, Competition, "competition")
    instance(season, Season, "season")
    instance(participants, Sequence, "participants")
    instance(entries, Sequence, "entries")

    if event.sport_id != sport.sport_id:
        raise ValueError("event.sport_id does not match sport")
    if competition.sport_id != sport.sport_id:
        raise ValueError("competition.sport_id does not match sport")
    if event.competition_id != competition.competition_id:
        raise ValueError("event.competition_id does not match competition")
    if season.competition_id != competition.competition_id:
        raise ValueError("season.competition_id does not match competition")
    if event.season_id != season.season_id:
        raise ValueError("event.season_id does not match season")

    participant_ids: set[ParticipantId] = set()
    for participant in participants:
        instance(participant, Participant, "participants member")
        if participant.sport_id != sport.sport_id:
            raise ValueError("participant.sport_id does not match sport")
        if participant.participant_id in participant_ids:
            raise ValueError("duplicate participant record")
        participant_ids.add(participant.participant_id)

    if not entries:
        raise ValueError("event context requires at least one entry")
    attached_ids: set[ParticipantId] = set()
    for entry in entries:
        instance(entry, EventParticipant, "entries member")
        if entry.event_id != event.event_id:
            raise ValueError("entry.event_id does not match event")
        if entry.participant_id not in participant_ids:
            raise ValueError("entry references a missing participant")
        if entry.participant_id in attached_ids:
            raise ValueError("duplicate entry for participant")
        attached_ids.add(entry.participant_id)

    if participant_ids != attached_ids:
        raise ValueError("unattached participant in event context")
