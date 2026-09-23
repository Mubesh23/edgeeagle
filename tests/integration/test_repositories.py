"""Real PostgreSQL transaction semantics in a newly migrated disposable database."""

import os
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy import URL, Engine, create_engine, text
from sqlalchemy.exc import IntegrityError

from edgeeagle_domain.provenance import (
    DataSource,
    DataSourceId,
    SourceType,
    Venue,
    VenueId,
    VenueType,
)
from edgeeagle_domain.repositories import (
    DataSourceRepository,
    DuplicateRecordError,
    VenueRepository,
)
from edgeeagle_persistence.provenance import PostgresDataSourceRepository, PostgresVenueRepository


@pytest.fixture
def repository_engine() -> Iterator[Engine]:
    database = f"edgeeagle_repository_test_{uuid4().hex}"
    port = int(os.environ.get("EDGEEAGLE_POSTGRES_PORT", "55432"))
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
                command.upgrade(config, "head")
            yield engine
        finally:
            engine.dispose()
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database)))


def source(identity: str = "same-id", capabilities: frozenset[str] = frozenset()) -> DataSource:
    return DataSource(
        data_source_id=DataSourceId(identity),
        code="FIXTURE'; --",
        source_type=SourceType.ODDS_AGGREGATOR,
        capabilities=capabilities,
    )


def venue(capabilities: frozenset[str] = frozenset()) -> Venue:
    return Venue(
        venue_id=VenueId("same-id"),
        operator="Fixture",
        product="test",
        jurisdiction="synthetic-only",
        venue_type=VenueType.EXCHANGE,
        capabilities=capabilities,
    )


@pytest.mark.parametrize("capabilities", [frozenset(), frozenset({"quotes", "history"})])
def test_repository_round_trip_and_commit(
    repository_engine: Engine,
    capabilities: frozenset[str],
) -> None:
    expected_source, expected_venue = source(capabilities=capabilities), venue(capabilities)
    with repository_engine.begin() as connection:
        sources: DataSourceRepository = PostgresDataSourceRepository(connection)
        venues: VenueRepository = PostgresVenueRepository(connection)
        assert sources.get(DataSourceId("absent")) is None
        assert venues.get(VenueId("absent")) is None
        sources.add(expected_source)
        venues.add(expected_venue)
        assert sources.get(expected_source.data_source_id) == expected_source
        assert venues.get(expected_venue.venue_id) == expected_venue
        with repository_engine.begin() as other:
            assert PostgresDataSourceRepository(other).get(expected_source.data_source_id) is None
            assert PostgresVenueRepository(other).get(expected_venue.venue_id) is None
    with repository_engine.begin() as connection:
        assert (
            PostgresDataSourceRepository(connection).get(expected_source.data_source_id)
            == expected_source
        )
        assert PostgresVenueRepository(connection).get(expected_venue.venue_id) == expected_venue


def test_repository_outer_failure_rolls_back_both_records(repository_engine: Engine) -> None:
    with pytest.raises(RuntimeError, match="abort"), repository_engine.begin() as connection:
        PostgresDataSourceRepository(connection).add(source(capabilities=frozenset({"quotes"})))
        PostgresVenueRepository(connection).add(venue(frozenset({"quotes"})))
        raise RuntimeError("abort")
    with repository_engine.begin() as connection:
        assert PostgresDataSourceRepository(connection).get(DataSourceId("same-id")) is None
        assert PostgresVenueRepository(connection).get(VenueId("same-id")) is None
        assert connection.scalar(text("SELECT count(*) FROM data_source_capabilities")) == 0
        assert connection.scalar(text("SELECT count(*) FROM venue_capabilities")) == 0


def test_repository_duplicate_does_not_overwrite_or_poison_transaction(
    repository_engine: Engine,
) -> None:
    with repository_engine.begin() as connection:
        sources = PostgresDataSourceRepository(connection)
        venues = PostgresVenueRepository(connection)
        sources.add(source())
        venues.add(venue())
        with pytest.raises(DuplicateRecordError):
            sources.add(source(capabilities=frozenset({"history"})))
        with pytest.raises(DuplicateRecordError):
            venues.add(venue(frozenset({"history"})))
        assert sources.get(DataSourceId("same-id")) == source()
        assert venues.get(VenueId("same-id")) == venue()
        sources.add(source("next"))
    with repository_engine.begin() as connection:
        assert PostgresDataSourceRepository(connection).get(DataSourceId("next")) == source("next")


def test_repository_requires_active_non_autocommit_transaction(repository_engine: Engine) -> None:
    with repository_engine.connect() as connection:
        repository = PostgresDataSourceRepository(connection)
        with pytest.raises(RuntimeError, match="active caller-owned"):
            repository.get(DataSourceId("missing"))
        with connection.begin():
            assert repository.get(DataSourceId("missing")) is None
        with pytest.raises(RuntimeError, match="active caller-owned"):
            repository.add(source())
        connection.execution_options(isolation_level="AUTOCOMMIT")
        with connection.begin(), pytest.raises(RuntimeError, match="Autocommit"):
            repository.add(source())


@pytest.mark.parametrize("kind", ["source", "venue"])
def test_repository_child_failure_rolls_back_parent_and_preserves_other_work(
    repository_engine: Engine,
    kind: str,
) -> None:
    # Test-only constraint forces failure after parent INSERT, without mocking SQL.
    table = "data_source_capabilities" if kind == "source" else "venue_capabilities"
    with repository_engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE {table} ADD CHECK (capability <> 'reject')"))
        sources, venues = (
            PostgresDataSourceRepository(connection),
            PostgresVenueRepository(connection),
        )
        sources.add(source("preserved"))
        with pytest.raises(IntegrityError):
            if kind == "source":
                sources.add(source(capabilities=frozenset({"accept", "reject"})))
            else:
                venues.add(venue(frozenset({"accept", "reject"})))
        assert sources.get(DataSourceId("same-id")) is None
        assert venues.get(VenueId("same-id")) is None
        assert connection.scalar(text(f"SELECT count(*) FROM {table}")) == 0
    with repository_engine.begin() as connection:
        assert PostgresDataSourceRepository(connection).get(DataSourceId("preserved")) == source(
            "preserved"
        )
