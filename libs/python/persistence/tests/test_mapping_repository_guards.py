"""No-network shape checks at the mapping persistence boundary."""

from datetime import datetime
from unittest.mock import create_autospec

import pytest
from sqlalchemy import Connection

from edgeeagle_domain.mappings import ProviderEntityKey
from edgeeagle_domain.provenance import DataSourceId
from edgeeagle_persistence.mappings import PostgresMappingRepository


def test_mapping_repository_invalid_inputs_never_execute_sql() -> None:
    connection = create_autospec(Connection, instance=True)
    repository = PostgresMappingRepository(connection)
    with pytest.raises(TypeError, match="ProviderMappingRevision"):
        repository.append(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="ProviderEntityKey"):
        repository.history(object())  # type: ignore[arg-type]
    key = ProviderEntityKey(
        data_source_id=DataSourceId("s"), provider_entity_type="fixture", provider_entity_id="id"
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        repository.resolve(key, as_of=datetime(2026, 1, 1))
    connection.execute.assert_not_called()
