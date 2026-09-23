"""Pinned read-only reference composition for the fixture normalizer (ADR-025)."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import Connection, Engine, text

from edgeeagle_ingestion.fixture_references import (
    FixtureReferenceKeys,
    FixtureReferenceReads,
    FixtureReferenceResolver,
    ResolvedFixtureReferences,
    resolve_fixture_references,
)
from edgeeagle_persistence._transactions import require_transaction
from edgeeagle_persistence.mappings import PostgresMappingRepository
from edgeeagle_persistence.sports import PostgresSportsRepository


class PostgresFixtureReferenceResolver:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def resolve(self, keys: FixtureReferenceKeys, *, as_of: datetime) -> ResolvedFixtureReferences:
        require_transaction(self._connection)
        if self._connection.get_isolation_level() != "REPEATABLE READ":
            raise RuntimeError("Fixture resolution requires REPEATABLE READ isolation")
        if self._connection.scalar(text("SHOW transaction_read_only")) != "on":
            raise RuntimeError("Fixture resolution requires a read-only transaction")
        return resolve_fixture_references(
            keys,
            PostgresMappingRepository(self._connection),
            PostgresSportsRepository(self._connection),
            as_of=as_of,
        )


def fixture_reference_reads(engine: Engine) -> FixtureReferenceReads:
    """One fresh snapshot per batch, never join an acceptance transaction.

    Caller owns engine lifecycle and connection/pool timeouts. SQL and idle-in-
    transaction waits are bounded here; no credentials, migration, seed, or retry.
    Raw storage I/O occurs before this context in the ingestion normalizer.
    """

    @contextmanager
    def reads() -> Iterator[FixtureReferenceResolver]:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            with connection.begin():
                connection.execute(text("SET TRANSACTION READ ONLY"))
                connection.execute(text("SET LOCAL statement_timeout = '5s'"))
                connection.execute(text("SET LOCAL idle_in_transaction_session_timeout = '5s'"))
                yield PostgresFixtureReferenceResolver(connection)

    return reads
