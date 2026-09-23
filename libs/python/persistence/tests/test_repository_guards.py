"""No-network adapter guards reject wrong identities before attempting SQL."""

from types import SimpleNamespace
from unittest.mock import create_autospec

import pytest
from sqlalchemy import Connection

from edgeeagle_domain.provenance import DataSourceId, VenueId
from edgeeagle_persistence.provenance import PostgresDataSourceRepository, PostgresVenueRepository


def test_wrong_namespace_and_record_types_never_execute_sql() -> None:
    connection = create_autospec(Connection, instance=True)
    sources = PostgresDataSourceRepository(connection)
    venues = PostgresVenueRepository(connection)
    with pytest.raises(TypeError, match="DataSourceId"):
        sources.get(VenueId("same"))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="VenueId"):
        venues.get(DataSourceId("same"))  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="DataSource"):
        sources.add(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="Venue"):
        venues.add(object())  # type: ignore[arg-type]
    connection.execute.assert_not_called()


def test_wrong_database_is_rejected_before_sql() -> None:
    connection = create_autospec(Connection, instance=True)
    connection.dialect = SimpleNamespace(name="sqlite")
    with pytest.raises(ValueError, match="PostgreSQL"):
        PostgresDataSourceRepository(connection).get(DataSourceId("missing"))
    connection.execute.assert_not_called()
