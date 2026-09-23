"""Exercise migrations in an isolated database, never resetting application data."""

import os
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy import URL, Connection, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from tests.integration.sports_schema import assert_sports_constraints


def assert_source_venue_constraints(connection: Connection) -> None:
    """Exercise actual PostgreSQL constraints with savepoints after each rejection."""
    source_insert = (
        "INSERT INTO data_sources (data_source_id, code, source_type) VALUES (:id, :code, :kind)"
    )
    connection.execute(
        text(source_insert), {"id": "same-id", "code": "THE_ODDS_API", "kind": "ODDS_AGGREGATOR"}
    )
    connection.execute(
        text(
            "INSERT INTO venues (venue_id, operator, product, jurisdiction, venue_type) "
            "VALUES ('same-id', 'Bovada', 'fixture', 'fixture-only', 'SPORTSBOOK')"
        )
    )
    connection.execute(
        text("INSERT INTO data_source_capabilities VALUES ('same-id', 'market_data')")
    )
    connection.execute(text("INSERT INTO venue_capabilities VALUES ('same-id', 'market_data')"))
    assert connection.scalar(text("SELECT code FROM data_sources")) == "THE_ODDS_API"
    assert connection.scalar(text("SELECT operator FROM venues")) == "Bovada"
    assert (
        connection.scalar(text("SELECT capability FROM data_source_capabilities")) == "market_data"
    )

    for value in ("", " padded", "trailing ", "\t", "\nname"):
        with pytest.raises(IntegrityError) as error, connection.begin_nested():
            connection.execute(
                text(source_insert), {"id": value, "code": "FIXTURE", "kind": "SPORTS_DATA"}
            )
        assert isinstance(error.value.orig, psycopg.Error)
        assert error.value.orig.sqlstate == "23514"

    invalid_sql = [
        ("INSERT INTO data_sources VALUES ('new', 'FIXTURE', 'UNKNOWN')", "23514"),
        ("INSERT INTO data_sources VALUES ('new', '', 'SPORTS_DATA')", "23514"),
        ("INSERT INTO data_sources VALUES ('new', NULL, 'SPORTS_DATA')", "23502"),
        ("INSERT INTO data_sources VALUES ('same-id', 'OTHER', 'SPORTS_DATA')", "23505"),
        ("INSERT INTO venues VALUES ('new', 'V', 'P', 'J', 'UNKNOWN')", "23514"),
        ("INSERT INTO venues VALUES ('new', '', 'P', 'J', 'EXCHANGE')", "23514"),
        ("INSERT INTO venues VALUES ('new', 'V', '', 'J', 'EXCHANGE')", "23514"),
        ("INSERT INTO venues VALUES ('new', 'V', 'P', '', 'EXCHANGE')", "23514"),
    ]
    for table, id_column, parent in (
        ("data_source_capabilities", "data_source_id", "data_sources"),
        ("venue_capabilities", "venue_id", "venues"),
    ):
        invalid_sql.extend(
            [
                (f"INSERT INTO {table} VALUES ('missing', 'market_data')", "23503"),
                (f"INSERT INTO {table} VALUES ('same-id', 'market_data')", "23505"),
                (f"INSERT INTO {table} VALUES ('same-id', '')", "23514"),
                (f"INSERT INTO {table} VALUES ('same-id', NULL)", "23502"),
                (f"DELETE FROM {parent} WHERE {id_column} = 'same-id'", "23503"),
            ]
        )
    for statement, sqlstate in invalid_sql:
        with pytest.raises(IntegrityError) as error, connection.begin_nested():
            connection.execute(text(statement))
        assert isinstance(error.value.orig, psycopg.Error)
        assert error.value.orig.sqlstate == sqlstate

    # Empty capability sets require no sentinel rows; all documented categories work.
    for kind in ("SPORTS_DATA", "VENUE_API", "OFFLINE_DATASET"):
        connection.execute(text(source_insert), {"id": kind, "code": kind, "kind": kind})
    for kind in ("PREDICTION_MARKET", "EXCHANGE"):
        connection.execute(
            text("INSERT INTO venues VALUES (:id, 'fixture', 'fixture', 'fixture-only', :kind)"),
            {"id": kind, "kind": kind},
        )


def test_migration_upgrade_repeat_downgrade_and_reapply() -> None:
    port = int(os.environ.get("EDGEEAGLE_POSTGRES_PORT", "55432"))
    database = f"edgeeagle_migration_test_{uuid4().hex}"
    with psycopg.connect(
        host="127.0.0.1",
        port=port,
        user="edgeeagle",
        password="edgeeagle-local",
        dbname="postgres",
        connect_timeout=5,
        autocommit=True,
    ) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        engine = create_engine(
            URL.create(
                "postgresql+psycopg",
                username="edgeeagle",
                password="edgeeagle-local",
                host="127.0.0.1",
                port=port,
                database=database,
            ),
            connect_args={"connect_timeout": 5},
        )
        try:
            config = Config(str(Path(__file__).resolve().parents[2] / "apps/api/alembic.ini"))
            with engine.begin() as connection:
                config.attributes["connection"] = connection
                command.upgrade(config, "0001_foundation")
                connection.execute(text("CREATE TABLE migration_sentinel (value text NOT NULL)"))
                connection.execute(text("INSERT INTO migration_sentinel VALUES ('preserved')"))
                command.upgrade(config, "0002_source_venue")
                assert_source_venue_constraints(connection)
                command.upgrade(config, "head")
                command.upgrade(config, "head")
                assert connection.scalars(
                    text("SELECT version_num FROM alembic_version")
                ).all() == ["0003_sports_events"]
                assert_sports_constraints(connection)
            # A separate transaction must observe the committed migration state.
            with engine.begin() as connection:
                config.attributes["connection"] = connection
                assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                    "0003_sports_events"
                )
                assert connection.scalar(text("SELECT count(*) FROM data_sources")) == 4
                assert connection.scalar(text("SELECT count(*) FROM event_participants")) == 12
                command.downgrade(config, "0002_source_venue")
                assert connection.scalar(text("SELECT count(*) FROM data_sources")) == 4
                assert "sports" not in inspect(connection).get_table_names()
                command.upgrade(config, "head")
                assert_sports_constraints(connection)
                command.downgrade(config, "base")
                assert connection.scalar(text("SELECT count(*) FROM alembic_version")) == 0
                assert set(inspect(connection).get_table_names()) == {
                    "alembic_version",
                    "migration_sentinel",
                }
                assert (
                    connection.scalar(text("SELECT value FROM migration_sentinel")) == "preserved"
                )
                command.upgrade(config, "head")
                assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                    "0003_sports_events"
                )
                assert_source_venue_constraints(connection)
                assert_sports_constraints(connection)
        finally:
            engine.dispose()
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database)))
