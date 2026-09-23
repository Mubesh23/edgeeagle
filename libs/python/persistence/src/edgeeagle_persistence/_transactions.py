"""Shared guards and insert savepoints for PostgreSQL adapters."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Connection
from sqlalchemy.exc import IntegrityError

from edgeeagle_domain.repositories import DuplicateRecordError


def require_transaction(connection: Connection) -> None:
    if connection.dialect.name != "postgresql":
        raise ValueError("PostgreSQL is required")
    if not connection.in_transaction():
        raise RuntimeError("An active caller-owned transaction is required")
    # SQLAlchemy may report a logical transaction even with DBAPI autocommit enabled.
    dbapi_connection = connection.connection.dbapi_connection
    assert dbapi_connection is not None  # An active SQLAlchemy connection owns its DBAPI handle.
    if dbapi_connection.autocommit:
        raise RuntimeError("Autocommit connections are not supported")


@contextmanager
def insert(connection: Connection) -> Iterator[None]:
    require_transaction(connection)
    try:
        # Keep parent/child writes atomic even if the caller catches their error.
        with connection.begin_nested():
            yield
    except IntegrityError as error:
        if getattr(error.orig, "sqlstate", None) == "23505":
            raise DuplicateRecordError("Canonical identity already exists") from error
        raise
