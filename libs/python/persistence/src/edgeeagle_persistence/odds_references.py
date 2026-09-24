"""Pinned read-only provider mapping and canonical context reads (ADR-035)."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import Connection, Engine, text

from edgeeagle_ingestion.odds_references import (
    OddsReferenceKeys,
    OddsReferenceReads,
    OddsReferenceResolver,
    ResolvedOddsReferences,
    resolve_odds_references,
)
from edgeeagle_persistence._transactions import require_transaction
from edgeeagle_persistence.mappings import PostgresMappingRepository
from edgeeagle_persistence.provenance import PostgresDataSourceRepository, PostgresVenueRepository
from edgeeagle_persistence.sports import PostgresSportsRepository


class PostgresOddsReferenceResolver:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def resolve(self, keys: OddsReferenceKeys, *, as_of: datetime) -> ResolvedOddsReferences:
        require_transaction(self._connection)
        if self._connection.get_isolation_level() != "REPEATABLE READ":
            raise RuntimeError("Odds resolution requires REPEATABLE READ isolation")
        if self._connection.scalar(text("SHOW transaction_read_only")) != "on":
            raise RuntimeError("Odds resolution requires a read-only transaction")
        return resolve_odds_references(
            keys,
            PostgresMappingRepository(self._connection),
            PostgresSportsRepository(self._connection),
            PostgresDataSourceRepository(self._connection),
            PostgresVenueRepository(self._connection),
            as_of=as_of,
        )


def odds_reference_reads(engine: Engine) -> OddsReferenceReads:
    """One snapshot per capture; no storage I/O or acceptance transaction inside.

    Caller owns engine lifecycle and connection/pool timeouts. No migrations,
    reference writes, credentials, provider requests or automatic retries.
    """

    @contextmanager
    def reads() -> Iterator[OddsReferenceResolver]:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            with connection.begin():
                connection.execute(text("SET TRANSACTION READ ONLY"))
                connection.execute(text("SET LOCAL statement_timeout = '5s'"))
                connection.execute(text("SET LOCAL idle_in_transaction_session_timeout = '5s'"))
                yield PostgresOddsReferenceResolver(connection)

    return reads
