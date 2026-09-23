"""Parameterized current-state event reads using existing canonical tables."""

from sqlalchemy import Connection, text

from edgeeagle_domain._validation import instance
from edgeeagle_domain.event_query import EventPage, EventQuery
from edgeeagle_domain.sports import (
    CompetitionId,
    Event,
    EventId,
    EventParticipant,
    SeasonId,
    SportId,
)
from edgeeagle_persistence._transactions import require_transaction
from edgeeagle_persistence.sports import PostgresSportsRepository


class PostgresEventReader:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection
        self._sports = PostgresSportsRepository(connection)

    def get_event(self, event_id: EventId) -> Event | None:
        return self._sports.get_event(event_id)

    def get_event_participants(self, event_id: EventId) -> tuple[EventParticipant, ...]:
        return self._sports.get_event_participants(event_id)

    def list_events(self, query: EventQuery) -> EventPage:
        instance(query, EventQuery, "query")
        require_transaction(self._connection)
        clauses = []
        parameters: dict[str, str | int] = {"count": query.limit + 1}
        for column, value, operator in (
            ("event_id", query.after_event_id, ">"),
            ("sport_id", query.sport_id, "="),
            ("competition_id", query.competition_id, "="),
        ):
            if value is not None:
                clauses.append(f"{column} {operator} :{column}")
                parameters[column] = value.value
        if query.status is not None:
            clauses.append("status = :status")
            parameters["status"] = query.status
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        rows = (
            self._connection.execute(
                text(
                    "SELECT event_id, sport_id, competition_id, season_id, starts_at, status, "
                    "venue_location FROM events" + where + " ORDER BY event_id LIMIT :count"
                ),
                parameters,
            )
            .mappings()
            .all()
        )
        items = tuple(
            Event(
                event_id=EventId(row["event_id"]),
                sport_id=SportId(row["sport_id"]),
                competition_id=CompetitionId(row["competition_id"]),
                season_id=SeasonId(row["season_id"]),
                starts_at=row["starts_at"],
                status=row["status"],
                venue_location=row["venue_location"],
            )
            for row in rows[: query.limit]
        )
        return EventPage(items, items[-1].event_id if len(rows) > query.limit else None)
