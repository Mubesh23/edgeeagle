"""Provider reference reads pin all canonical records and mapping histories together."""

from dataclasses import replace

import pytest
from sqlalchemy import Engine, text

from edgeeagle_domain.mappings import MappingStatus
from edgeeagle_ingestion.odds_references import resolve_odds_references
from edgeeagle_persistence.mappings import PostgresMappingRepository
from edgeeagle_persistence.odds_references import (
    PostgresOddsReferenceResolver,
    odds_reference_reads,
)
from edgeeagle_persistence.provenance import PostgresDataSourceRepository, PostgresVenueRepository
from edgeeagle_persistence.sports import PostgresSportsRepository
from tests.integration.test_event_acceptance import seed
from tests.integration.test_repositories import repository_engine as repository_engine
from tests.unit.test_fixture_references import NOW
from tests.unit.test_odds_references import setup_references


def test_odds_reference_snapshot_and_revocation(repository_engine: Engine) -> None:
    args = setup_references()
    expected = resolve_odds_references(*args, as_of=NOW)
    with repository_engine.begin() as conn:
        seed(conn, include_source=False)
        PostgresDataSourceRepository(conn).add(expected.source)
        for venue in expected.venues:
            PostgresVenueRepository(conn).add(venue)
        PostgresSportsRepository(conn).add_event(expected.event, expected.entries)
        for row in expected.revisions:
            PostgresMappingRepository(conn).append(row)
    with odds_reference_reads(repository_engine)() as reader:
        assert reader.resolve(args[0], as_of=NOW) == expected
        with repository_engine.begin() as writer:
            PostgresMappingRepository(writer).append(
                replace(expected.revisions[1], revision=2, status=MappingStatus.REVOKED)
            )
        assert reader.resolve(args[0], as_of=NOW) == expected
    with odds_reference_reads(repository_engine)() as reader:
        with pytest.raises(ValueError, match="revoked"):
            reader.resolve(args[0], as_of=NOW)
    assert expected.revisions[1].revision == 1


def test_odds_reference_transaction_guards(repository_engine: Engine) -> None:
    keys = setup_references()[0]
    with repository_engine.connect() as conn:
        with pytest.raises(RuntimeError):
            PostgresOddsReferenceResolver(conn).resolve(keys, as_of=NOW)
        with conn.begin():
            with pytest.raises(RuntimeError, match="REPEATABLE READ"):
                PostgresOddsReferenceResolver(conn).resolve(keys, as_of=NOW)
    with repository_engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        with conn.begin():
            with pytest.raises(RuntimeError, match="read-only"):
                PostgresOddsReferenceResolver(conn).resolve(keys, as_of=NOW)
    with odds_reference_reads(repository_engine)() as reader:
        # The composed connection is tested only here to verify protective settings.
        conn = reader._connection  # type: ignore[attr-defined]
        assert conn.scalar(text("SHOW transaction_read_only")) == "on"
        assert conn.scalar(text("SHOW statement_timeout")) == "5s"
        assert conn.scalar(text("SHOW idle_in_transaction_session_timeout")) == "5s"
