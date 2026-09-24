"""One pinned read-only snapshot for Sportmonks reference evidence (ADR-037)."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import Connection, Engine, text

from edgeeagle_ingestion.sportmonks_references import (
    ResolvedSportmonksReferences,
    SportmonksReferenceKeys,
    SportmonksReferenceReads,
    SportmonksReferenceResolver,
    resolve_sportmonks_references,
)
from edgeeagle_persistence._transactions import require_transaction
from edgeeagle_persistence.mappings import PostgresMappingRepository
from edgeeagle_persistence.provenance import PostgresDataSourceRepository
from edgeeagle_persistence.sports import PostgresSportsRepository


class PostgresSportmonksReferenceResolver:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def resolve(
        self, keys: SportmonksReferenceKeys, *, as_of: datetime
    ) -> ResolvedSportmonksReferences:
        require_transaction(self._connection)
        if self._connection.get_isolation_level() != "REPEATABLE READ":
            raise RuntimeError("Sportmonks resolution requires REPEATABLE READ isolation")
        if self._connection.scalar(text("SHOW transaction_read_only")) != "on":
            raise RuntimeError("Sportmonks resolution requires a read-only transaction")
        return resolve_sportmonks_references(
            keys,
            PostgresMappingRepository(self._connection),
            PostgresSportsRepository(self._connection),
            PostgresDataSourceRepository(self._connection),
            as_of=as_of,
        )


def sportmonks_reference_reads(engine: Engine) -> SportmonksReferenceReads:
    """Caller owns engine/pool lifecycle; no raw I/O, writes, migrations or retries."""

    @contextmanager
    def reads() -> Iterator[SportmonksReferenceResolver]:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            with connection.begin():
                connection.execute(text("SET TRANSACTION READ ONLY"))
                connection.execute(text("SET LOCAL statement_timeout = '5s'"))
                connection.execute(text("SET LOCAL idle_in_transaction_session_timeout = '5s'"))
                yield PostgresSportmonksReferenceResolver(connection)

    return reads
