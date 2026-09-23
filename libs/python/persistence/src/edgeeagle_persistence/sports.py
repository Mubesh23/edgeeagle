"""Current-state sports persistence, with atomic validated event insertion."""

from sqlalchemy import Connection, text

from edgeeagle_domain._validation import instance
from edgeeagle_domain.consistency import validate_event_context
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
from edgeeagle_persistence._transactions import insert, require_transaction


class PostgresSportsRepository:
    """Operate inside the supplied caller-owned PostgreSQL transaction."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def add_sport(self, sport: Sport) -> None:
        instance(sport, Sport, "sport")
        with insert(self._connection):
            self._connection.execute(
                text("INSERT INTO sports (sport_id, code, name) VALUES (:sport_id, :code, :name)"),
                {
                    "sport_id": sport.sport_id.value,
                    "code": sport.code,
                    "name": sport.name,
                },
            )

    def get_sport(self, sport_id: SportId) -> Sport | None:
        instance(sport_id, SportId, "sport_id")
        require_transaction(self._connection)
        row = (
            self._connection.execute(
                text("SELECT sport_id, code, name FROM sports WHERE sport_id = :id"),
                {"id": sport_id.value},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return Sport(
            sport_id=SportId(row["sport_id"]),
            code=row["code"],
            name=row["name"],
        )

    def add_competition(self, competition: Competition) -> None:
        instance(competition, Competition, "competition")
        with insert(self._connection):
            self._connection.execute(
                text(
                    "INSERT INTO competitions "
                    "(competition_id, sport_id, name, country_or_region, gender_or_division) "
                    "VALUES (:competition_id, :sport_id, :name, "
                    ":country_or_region, :gender_or_division)"
                ),
                {
                    "competition_id": competition.competition_id.value,
                    "sport_id": competition.sport_id.value,
                    "name": competition.name,
                    "country_or_region": competition.country_or_region,
                    "gender_or_division": competition.gender_or_division,
                },
            )

    def get_competition(self, competition_id: CompetitionId) -> Competition | None:
        instance(competition_id, CompetitionId, "competition_id")
        require_transaction(self._connection)
        row = (
            self._connection.execute(
                text(
                    "SELECT competition_id, sport_id, name, country_or_region, gender_or_division "
                    "FROM competitions WHERE competition_id = :id"
                ),
                {"id": competition_id.value},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return Competition(
            competition_id=CompetitionId(row["competition_id"]),
            sport_id=SportId(row["sport_id"]),
            name=row["name"],
            country_or_region=row["country_or_region"],
            gender_or_division=row["gender_or_division"],
        )

    def add_season(self, season: Season) -> None:
        instance(season, Season, "season")
        with insert(self._connection):
            self._connection.execute(
                text(
                    "INSERT INTO seasons (season_id, competition_id, name, starts_at, ends_at) "
                    "VALUES (:season_id, :competition_id, :name, :starts_at, :ends_at)"
                ),
                {
                    "season_id": season.season_id.value,
                    "competition_id": season.competition_id.value,
                    "name": season.name,
                    "starts_at": season.starts_at,
                    "ends_at": season.ends_at,
                },
            )

    def get_season(self, season_id: SeasonId) -> Season | None:
        instance(season_id, SeasonId, "season_id")
        require_transaction(self._connection)
        row = (
            self._connection.execute(
                text(
                    "SELECT season_id, competition_id, name, starts_at, ends_at "
                    "FROM seasons WHERE season_id = :id"
                ),
                {"id": season_id.value},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return Season(
            season_id=SeasonId(row["season_id"]),
            competition_id=CompetitionId(row["competition_id"]),
            name=row["name"],
            starts_at=row["starts_at"],
            ends_at=row["ends_at"],
        )

    def add_participant(self, participant: Participant) -> None:
        instance(participant, Participant, "participant")
        with insert(self._connection):
            self._connection.execute(
                text(
                    "INSERT INTO participants "
                    "(participant_id, sport_id, participant_type, canonical_name) "
                    "VALUES (:participant_id, :sport_id, :participant_type, :canonical_name)"
                ),
                {
                    "participant_id": participant.participant_id.value,
                    "sport_id": participant.sport_id.value,
                    "participant_type": participant.participant_type,
                    "canonical_name": participant.canonical_name,
                },
            )

    def get_participant(self, participant_id: ParticipantId) -> Participant | None:
        instance(participant_id, ParticipantId, "participant_id")
        require_transaction(self._connection)
        row = (
            self._connection.execute(
                text(
                    "SELECT participant_id, sport_id, participant_type, canonical_name "
                    "FROM participants WHERE participant_id = :id"
                ),
                {"id": participant_id.value},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return Participant(
            participant_id=ParticipantId(row["participant_id"]),
            sport_id=SportId(row["sport_id"]),
            participant_type=row["participant_type"],
            canonical_name=row["canonical_name"],
        )

    def get_event(self, event_id: EventId) -> Event | None:
        instance(event_id, EventId, "event_id")
        require_transaction(self._connection)
        row = (
            self._connection.execute(
                text(
                    "SELECT event_id, sport_id, competition_id, season_id, "
                    "starts_at, status, venue_location "
                    "FROM events WHERE event_id = :id"
                ),
                {"id": event_id.value},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        return Event(
            event_id=EventId(row["event_id"]),
            sport_id=SportId(row["sport_id"]),
            competition_id=CompetitionId(row["competition_id"]),
            season_id=SeasonId(row["season_id"]),
            starts_at=row["starts_at"],
            status=row["status"],
            venue_location=row["venue_location"],
        )

    def add_event(self, event: Event, entries: tuple[EventParticipant, ...]) -> None:
        instance(event, Event, "event")
        instance(entries, tuple, "entries")
        for entry in entries:
            instance(entry, EventParticipant, "entry")
        with insert(self._connection):
            sport = self.get_sport(event.sport_id)
            competition = self.get_competition(event.competition_id)
            season = self.get_season(event.season_id)
            if sport is None or competition is None or season is None:
                raise ValueError("Event references a missing sport, competition, or season")
            participants = []
            for participant_id in dict.fromkeys(entry.participant_id for entry in entries):
                participant = self.get_participant(participant_id)
                if participant is None:
                    raise ValueError("Event references a missing participant")
                participants.append(participant)
            validate_event_context(
                event=event,
                sport=sport,
                competition=competition,
                season=season,
                participants=participants,
                entries=entries,
            )
            self._connection.execute(
                text(
                    "INSERT INTO events "
                    "(event_id, sport_id, competition_id, season_id, "
                    "starts_at, status, venue_location) "
                    "VALUES (:id, :sport, :competition, :season, :starts_at, :status, :location)"
                ),
                {
                    "id": event.event_id.value,
                    "sport": event.sport_id.value,
                    "competition": event.competition_id.value,
                    "season": event.season_id.value,
                    "starts_at": event.starts_at,
                    "status": event.status,
                    "location": event.venue_location,
                },
            )
            self._connection.execute(
                text(
                    "INSERT INTO event_participants (event_id, participant_id, sport_id, role) "
                    "VALUES (:event, :participant, :sport, :role)"
                ),
                [
                    {
                        "event": event.event_id.value,
                        "participant": entry.participant_id.value,
                        "sport": event.sport_id.value,
                        "role": entry.role,
                    }
                    for entry in entries
                ],
            )

    def get_event_participants(self, event_id: EventId) -> tuple[EventParticipant, ...]:
        instance(event_id, EventId, "event_id")
        require_transaction(self._connection)
        rows = self._connection.execute(
            text(
                "SELECT event_id, participant_id, role FROM event_participants "
                "WHERE event_id = :id ORDER BY participant_id"
            ),
            {"id": event_id.value},
        ).mappings()
        return tuple(
            EventParticipant(
                event_id=EventId(row["event_id"]),
                participant_id=ParticipantId(row["participant_id"]),
                role=row["role"],
            )
            for row in rows
        )
