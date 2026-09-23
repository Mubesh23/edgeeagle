"""Mapping storage constraints, tested without any provider or production access."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, inspect, text
from sqlalchemy.exc import IntegrityError

from edgeeagle_persistence.provenance import PostgresDataSourceRepository, PostgresVenueRepository
from edgeeagle_persistence.sports import PostgresSportsRepository
from tests.integration.test_repositories import repository_engine as repository_engine
from tests.integration.test_repositories import source, venue
from tests.integration.test_sports_repository import ENTRIES, EVENT, seed

TARGETS = (
    ("SPORT", "sport_id", "s"),
    ("COMPETITION", "competition_id", "c"),
    ("SEASON", "season_id", "season"),
    ("PARTICIPANT", "participant_id", "p00"),
    ("EVENT", "event_id", "e"),
    ("VENUE", "venue_id", "same-id"),
)


def seed_targets(connection: Connection) -> None:
    PostgresDataSourceRepository(connection).add(source())
    PostgresVenueRepository(connection).add(venue())
    repository = PostgresSportsRepository(connection)
    seed(repository)
    repository.add_event(EVENT, ENTRIES)


def add_key(connection: Connection, kind: str = "SPORT", **overrides: object) -> None:
    values: dict[str, object] = dict(
        data_source_id="same-id",
        provider_entity_type="entity",
        provider_entity_id=kind,
        target_kind=kind,
    )
    values.update(overrides)
    connection.execute(
        text(
            "INSERT INTO provider_mapping_keys "
            "(data_source_id, provider_entity_type, provider_entity_id, target_kind) "
            "VALUES (:data_source_id, :provider_entity_type, :provider_entity_id, :target_kind)"
        ),
        values,
    )


def add_revision(connection: Connection, **overrides: object) -> None:
    values: dict[str, object] = dict(
        data_source_id="same-id",
        provider_entity_type="entity",
        provider_entity_id="SPORT",
        revision=1,
        target_kind="SPORT",
        sport_id="s",
        competition_id=None,
        season_id=None,
        participant_id=None,
        event_id=None,
        venue_id=None,
        mapping_method="fixture",
        confidence=Decimal("0.123456789123456789"),
        validated_by="fixture-reviewer",
        validated_at=datetime(2026, 1, 1, tzinfo=UTC),
        available_at=datetime(2026, 1, 1, tzinfo=UTC),
        ingested_at=datetime(2026, 1, 1, tzinfo=UTC),
        status="MAPPED",
    )
    values.update(overrides)
    columns = ", ".join(values)
    parameters = ", ".join(f":{name}" for name in values)
    connection.execute(
        text(f"INSERT INTO provider_mapping_revisions ({columns}) VALUES ({parameters})"), values
    )


def test_mapping_schema_targets_history_and_namespace(repository_engine: Engine) -> None:
    with repository_engine.begin() as connection:
        seed_targets(connection)
        for kind, column, identity in TARGETS:
            add_key(connection, kind)
            values: dict[str, object] = {
                "sport_id": None,
                column: identity,
                "provider_entity_id": kind,
                "target_kind": kind,
            }
            with pytest.raises(IntegrityError) as error, connection.begin_nested():
                add_revision(connection, **(values | {column: "missing"}))
            assert isinstance(error.value.orig, psycopg.Error)
            assert error.value.orig.sqlstate == "23503"
            add_revision(connection, **values)
        with pytest.raises(IntegrityError) as error, connection.begin_nested():
            connection.execute(text("DELETE FROM venues WHERE venue_id = 'same-id'"))
        assert isinstance(error.value.orig, psycopg.Error)
        assert error.value.orig.sqlstate == "23503"
        indexes = inspect(connection).get_indexes("provider_mapping_revisions")
        indexed_columns = {tuple(index["column_names"]) for index in indexes}
        for _, column, _ in TARGETS:
            assert (column,) in indexed_columns
        assert (
            "data_source_id",
            "provider_entity_type",
            "provider_entity_id",
            "previous_revision",
        ) in indexed_columns
        add_revision(connection, revision=2, status="REVOKED", confidence=None)
        add_revision(connection, revision=3, confidence=Decimal("1"))
        # Opaque, case-sensitive type/ID namespaces and separate sources do not collide.
        add_key(connection, provider_entity_id="sport")
        add_key(connection, provider_entity_type="Entity")
        PostgresDataSourceRepository(connection).add(source("other"))
        add_key(connection, data_source_id="other")
        add_revision(connection, data_source_id="other", confidence=Decimal("0"))
        assert connection.scalar(
            text(
                "SELECT confidence FROM provider_mapping_revisions "
                "WHERE provider_entity_id = 'SPORT' AND revision = 1 "
                "AND data_source_id = 'same-id'"
            )
        ) == Decimal("0.123456789123456789")
        assert connection.scalars(
            text(
                "SELECT previous_revision FROM provider_mapping_revisions "
                "WHERE provider_entity_id = 'SPORT' AND data_source_id = 'same-id' "
                "ORDER BY revision"
            )
        ).all() == [None, 1, 2]
    with repository_engine.begin() as connection:
        assert connection.scalar(text("SELECT count(*) FROM provider_mapping_revisions")) == 9


def test_mapping_schema_rejects_invalid_revisions(repository_engine: Engine) -> None:
    with repository_engine.begin() as connection:
        seed_targets(connection)
        add_key(connection)
        invalid: list[tuple[dict[str, object], str]] = [
            ({"revision": 0}, "23514"),
            ({"revision": 2}, "23503"),
            ({"status": "REVOKED"}, "23514"),
            ({"status": "UNKNOWN"}, "23514"),
            ({"sport_id": None}, "23514"),
            ({"venue_id": "same-id"}, "23514"),
            ({"sport_id": "missing"}, "23503"),
            ({"target_kind": "VENUE", "sport_id": None, "venue_id": "same-id"}, "23503"),
            ({"target_kind": "VENUE"}, "23514"),
            ({"confidence": Decimal("NaN")}, "23514"),
            ({"confidence": Decimal("Infinity")}, "23514"),
            ({"confidence": Decimal("-Infinity")}, "23514"),
            ({"confidence": Decimal("-0.1")}, "23514"),
            ({"confidence": Decimal("1.1")}, "23514"),
            ({"validated_by": " padded"}, "23514"),
            ({"mapping_method": ""}, "23514"),
            ({"validated_at": "infinity"}, "23514"),
            ({"available_at": "-infinity"}, "23514"),
            ({"ingested_at": "infinity"}, "23514"),
            ({"validated_at": datetime(2027, 1, 1, tzinfo=UTC)}, "23514"),
            ({"ingested_at": datetime(2025, 1, 1, tzinfo=UTC)}, "23514"),
            ({"data_source_id": "missing"}, "23503"),
            ({"provider_entity_id": "missing"}, "23503"),
            ({"validated_by": None}, "23502"),
        ]
        for overrides, expected in invalid:
            with pytest.raises(IntegrityError) as error, connection.begin_nested():
                add_revision(connection, **overrides)
            assert isinstance(error.value.orig, psycopg.Error)
            assert error.value.orig.sqlstate == expected, overrides
        add_revision(connection)
        with pytest.raises(IntegrityError), connection.begin_nested():
            add_revision(connection)
        with pytest.raises(IntegrityError), connection.begin_nested():
            add_revision(connection, revision=3)


def test_mapping_schema_rejects_mutations_and_bad_keys(repository_engine: Engine) -> None:
    with repository_engine.begin() as connection:
        seed_targets(connection)
        for overrides in (
            {"data_source_id": "missing"},
            {"provider_entity_id": ""},
            {"provider_entity_type": " padded"},
            {"target_kind": "UNKNOWN"},
        ):
            with pytest.raises(IntegrityError), connection.begin_nested():
                add_key(connection, **overrides)
        add_key(connection)
        add_revision(connection)
        for table in ("provider_mapping_keys", "provider_mapping_revisions"):
            for statement in (
                f"UPDATE {table} SET provider_entity_type = 'changed'",
                f"DELETE FROM {table}",
                f"TRUNCATE {table} CASCADE",
            ):
                with pytest.raises(IntegrityError) as error, connection.begin_nested():
                    connection.execute(text(statement))
                assert isinstance(error.value.orig, psycopg.Error)
                assert error.value.orig.sqlstate == "23514"
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(text("DELETE FROM sports WHERE sport_id = 's'"))
        assert connection.scalar(text("SELECT count(*) FROM provider_mapping_revisions")) == 1


def test_mapping_schema_downgrade_preserves_prior_tables(repository_engine: Engine) -> None:
    config = Config(str(Path(__file__).resolve().parents[2] / "apps/api/alembic.ini"))
    with repository_engine.begin() as connection:
        seed_targets(connection)
        add_key(connection)
        add_revision(connection)
        config.attributes["connection"] = connection
        command.downgrade(config, "0003_sports_events")
        assert "provider_mapping_keys" not in inspect(connection).get_table_names()
        assert (
            connection.scalar(text("SELECT to_regprocedure('edgeeagle_mapping_immutable()')"))
            is None
        )
        assert connection.scalar(text("SELECT count(*) FROM events")) == 1
        assert connection.scalar(text("SELECT count(*) FROM data_sources")) == 1
        command.upgrade(config, "head")
        add_key(connection)
        add_revision(connection)
