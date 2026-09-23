"""PostgreSQL sports-schema assertions, invoked by the migration round-trip test."""

from datetime import UTC, datetime

import psycopg
import pytest
from sqlalchemy import Connection, inspect, text
from sqlalchemy.exc import IntegrityError


def assert_sports_constraints(connection: Connection) -> None:
    inspector = inspect(connection)
    for table in ("competitions", "seasons", "participants", "events", "event_participants"):
        index_columns = [index["column_names"] for index in inspector.get_indexes(table)]
        for foreign_key in inspector.get_foreign_keys(table):
            assert foreign_key["constrained_columns"] in index_columns
    for suffix in ("a", "b"):
        connection.execute(
            text("INSERT INTO sports VALUES (:id, :id, 'Fixture sport')"), {"id": suffix}
        )
        connection.execute(
            text("INSERT INTO competitions VALUES (:id, :id, 'Fixture league', 'Global', NULL)"),
            {"id": suffix},
        )
        connection.execute(
            text("INSERT INTO seasons VALUES (:id, :id, '2026', '2026-01-01Z', '2026-12-31Z')"),
            {"id": suffix},
        )
    # Same-sport, different competition catches season mismatches independently of sport.
    connection.execute(
        text("INSERT INTO competitions VALUES ('c', 'a', 'Other', 'Global', 'Women')")
    )
    connection.execute(
        text("INSERT INTO seasons VALUES ('c', 'c', '2026', '2026-01-01Z', '2026-12-31Z')")
    )
    connection.execute(
        text(
            "INSERT INTO events VALUES ('event', 'a', 'a', 'a', "
            "'2027-01-01 03:00:00+03', 'RESCHEDULED', NULL)"
        )
    )
    # Date containment isn't an invariant. Many FIELD roles and individual participants are valid.
    for i in range(12):
        connection.execute(
            text("INSERT INTO participants VALUES (:id, 'a', 'PLAYER', :name)"),
            {"id": f"p{i}", "name": f"Player {i}"},
        )
        connection.execute(
            text("INSERT INTO event_participants VALUES ('event', :id, 'a', 'FIELD')"),
            {"id": f"p{i}"},
        )
    connection.execute(text("INSERT INTO participants VALUES ('other', 'b', 'PAIR', 'Other pair')"))
    assert connection.scalar(text("SELECT count(*) FROM event_participants")) == 12
    assert connection.scalar(text("SELECT starts_at FROM events")) == datetime(
        2027, 1, 1, tzinfo=UTC
    )

    rejected = [
        ("UPDATE competitions SET sport_id='missing' WHERE competition_id='c'", "23503"),
        ("UPDATE seasons SET competition_id='missing' WHERE season_id='c'", "23503"),
        ("UPDATE participants SET sport_id='missing' WHERE participant_id='other'", "23503"),
        ("UPDATE events SET sport_id='b'", "23503"),
        ("UPDATE events SET season_id='c'", "23503"),
        ("UPDATE events SET competition_id='c'", "23503"),
        ("UPDATE events SET season_id='missing'", "23503"),
        ("INSERT INTO event_participants VALUES ('event', 'other', 'a', 'FIELD')", "23503"),
        ("INSERT INTO event_participants VALUES ('event', 'other', 'b', 'FIELD')", "23503"),
        ("INSERT INTO event_participants VALUES ('event', 'missing', 'a', 'FIELD')", "23503"),
        ("INSERT INTO event_participants VALUES ('missing', 'p0', 'a', 'FIELD')", "23503"),
        ("INSERT INTO event_participants VALUES ('event', 'p0', 'a', 'AWAY')", "23505"),
        ("UPDATE seasons SET ends_at = starts_at - interval '1 second'", "23514"),
        ("UPDATE seasons SET ends_at = 'infinity'", "23514"),
        ("UPDATE events SET starts_at = '-infinity'", "23514"),
        ("UPDATE events SET status = ''", "23514"),
        ("UPDATE events SET venue_location = ' padded '", "23514"),
        ("UPDATE participants SET participant_type = ''", "23514"),
        ("UPDATE event_participants SET role = ''", "23514"),
        ("UPDATE competitions SET gender_or_division = ''", "23514"),
        ("UPDATE event_participants SET sport_id = NULL", "23502"),
        ("DELETE FROM sports WHERE sport_id='a'", "23503"),
        ("DELETE FROM competitions WHERE competition_id='a'", "23503"),
        ("DELETE FROM seasons WHERE season_id='a'", "23503"),
        ("DELETE FROM participants WHERE participant_id='p0'", "23503"),
        ("DELETE FROM events WHERE event_id='event'", "23503"),
        ("UPDATE participants SET sport_id='b' WHERE participant_id='p0'", "23503"),
        ("UPDATE competitions SET sport_id='b' WHERE competition_id='a'", "23503"),
    ]
    for statement, sqlstate in rejected:
        with pytest.raises(IntegrityError) as error, connection.begin_nested():
            connection.execute(text(statement))
        assert isinstance(error.value.orig, psycopg.Error)
        assert error.value.orig.sqlstate == sqlstate, statement
    # Partial events are representable until ingestion performs complete-context validation.
    connection.execute(
        text(
            "INSERT INTO events VALUES "
            "('partial', 'a', 'a', 'a', '2026-01-01Z', 'SCHEDULED', 'Stadium')"
        )
    )
    connection.execute(text("UPDATE seasons SET ends_at = starts_at WHERE season_id='b'"))
