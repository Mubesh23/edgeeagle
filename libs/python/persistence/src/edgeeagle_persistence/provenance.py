"""Synchronous PostgreSQL adapters using a caller-owned, non-autocommit transaction."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from edgeeagle_domain.provenance import (
    DataSource,
    DataSourceId,
    SourceType,
    Venue,
    VenueId,
    VenueType,
)
from edgeeagle_domain.repositories import DuplicateRecordError


def _require_transaction(connection: Connection) -> None:
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
def _insert(connection: Connection) -> Iterator[None]:
    _require_transaction(connection)
    try:
        # Keep a parent+capabilities write atomic even if the caller catches its error.
        with connection.begin_nested():
            yield
    except IntegrityError as error:
        if getattr(error.orig, "sqlstate", None) == "23505":
            raise DuplicateRecordError("Canonical identity already exists") from error
        raise


class PostgresDataSourceRepository:
    """Insert/read sources; never commit, close, or create the caller's connection."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def add(self, source: DataSource) -> None:
        if not isinstance(source, DataSource):
            raise TypeError("source must be a DataSource")
        with _insert(self._connection):
            self._connection.execute(
                text(
                    "INSERT INTO data_sources (data_source_id, code, source_type) "
                    "VALUES (:id, :code, :kind)"
                ),
                {
                    "id": source.data_source_id.value,
                    "code": source.code,
                    "kind": source.source_type.value,
                },
            )
            if source.capabilities:
                self._connection.execute(
                    text(
                        "INSERT INTO data_source_capabilities (data_source_id, capability) "
                        "VALUES (:id, :capability)"
                    ),
                    [
                        {"id": source.data_source_id.value, "capability": capability}
                        for capability in sorted(source.capabilities)
                    ],
                )

    def get(self, source_id: DataSourceId) -> DataSource | None:
        if not isinstance(source_id, DataSourceId):
            raise TypeError("source_id must be a DataSourceId")
        _require_transaction(self._connection)
        rows = (
            self._connection.execute(
                text(
                    "SELECT s.data_source_id, s.code, s.source_type, c.capability "
                    "FROM data_sources AS s LEFT JOIN data_source_capabilities AS c "
                    "ON s.data_source_id = c.data_source_id WHERE s.data_source_id = :id"
                ),
                {"id": source_id.value},
            )
            .mappings()
            .all()
        )
        if not rows:
            return None
        return DataSource(
            data_source_id=DataSourceId(rows[0]["data_source_id"]),
            code=rows[0]["code"],
            source_type=SourceType(rows[0]["source_type"]),
            capabilities=frozenset(
                row["capability"] for row in rows if row["capability"] is not None
            ),
        )


class PostgresVenueRepository:
    """Insert/read venues independently of sources, including equal ID strings."""

    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def add(self, venue: Venue) -> None:
        if not isinstance(venue, Venue):
            raise TypeError("venue must be a Venue")
        with _insert(self._connection):
            self._connection.execute(
                text(
                    "INSERT INTO venues (venue_id, operator, product, jurisdiction, venue_type) "
                    "VALUES (:id, :operator, :product, :jurisdiction, :kind)"
                ),
                {
                    "id": venue.venue_id.value,
                    "operator": venue.operator,
                    "product": venue.product,
                    "jurisdiction": venue.jurisdiction,
                    "kind": venue.venue_type.value,
                },
            )
            if venue.capabilities:
                self._connection.execute(
                    text(
                        "INSERT INTO venue_capabilities (venue_id, capability) "
                        "VALUES (:id, :capability)"
                    ),
                    [
                        {"id": venue.venue_id.value, "capability": capability}
                        for capability in sorted(venue.capabilities)
                    ],
                )

    def get(self, venue_id: VenueId) -> Venue | None:
        if not isinstance(venue_id, VenueId):
            raise TypeError("venue_id must be a VenueId")
        _require_transaction(self._connection)
        rows = (
            self._connection.execute(
                text(
                    "SELECT v.venue_id, v.operator, v.product, v.jurisdiction, "
                    "v.venue_type, c.capability "
                    "FROM venues AS v LEFT JOIN venue_capabilities AS c "
                    "ON v.venue_id = c.venue_id WHERE v.venue_id = :id"
                ),
                {"id": venue_id.value},
            )
            .mappings()
            .all()
        )
        if not rows:
            return None
        return Venue(
            venue_id=VenueId(rows[0]["venue_id"]),
            operator=rows[0]["operator"],
            product=rows[0]["product"],
            jurisdiction=rows[0]["jurisdiction"],
            venue_type=VenueType(rows[0]["venue_type"]),
            capabilities=frozenset(
                row["capability"] for row in rows if row["capability"] is not None
            ),
        )
