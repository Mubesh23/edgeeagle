"""Format-3 acceptance and safe schema rollout on disposable PostgreSQL."""

from dataclasses import replace

import pytest
from alembic import command
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from edgeeagle_ingestion.events import EventAcceptanceConflict, SoccerResultEvidence
from edgeeagle_persistence._event_snapshot import canonical
from edgeeagle_persistence.events import PostgresEventAcceptanceRepository
from tests.integration.test_event_acceptance import seed
from tests.integration.test_mapped_receipts import migration_config
from tests.integration.test_repositories import repository_engine as repository_engine
from tests.unit.test_mapped_receipts import mapped_candidate
from tests.unit.test_soccer_receipts import result_candidate


def test_soccer_receipt_commit_retry_conflict_and_downgrade_guard(
    repository_engine: Engine,
) -> None:
    value = result_candidate()
    with repository_engine.begin() as connection:
        seed(connection)
        repository = PostgresEventAcceptanceRepository(connection)
        assert repository.accept(value)
    with repository_engine.begin() as connection:
        repository = PostgresEventAcceptanceRepository(connection)
        assert repository.get(value.event.event_id) == canonical(value)
        assert not repository.accept(value)
        assert connection.scalar(text("SELECT snapshot->'format' FROM event_normalizations")) == 3
        with pytest.raises(EventAcceptanceConflict):
            repository.accept(
                replace(
                    value,
                    soccer_result=SoccerResultEvidence(
                        home_goals=0, away_goals=0, utc_offset_minutes=60
                    ),
                )
            )
        with pytest.raises(IntegrityError, match="format-3 receipts"), connection.begin_nested():
            command.downgrade(migration_config(connection), "0009_mapped_receipts")
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "0011_market_quotes"
        )
        assert repository.get(value.event.event_id) == canonical(value)
        assert connection.scalar(text("SELECT count(*) FROM events")) == 1


def test_soccer_receipt_old_schema_rejects_new_and_preserves_mapped(
    repository_engine: Engine,
) -> None:
    with repository_engine.begin() as connection:
        seed(connection)
        config = migration_config(connection)
        command.downgrade(config, "0009_mapped_receipts")
        repository = PostgresEventAcceptanceRepository(connection)
        with pytest.raises(IntegrityError):
            repository.accept(result_candidate())
        assert connection.scalar(text("SELECT count(*) FROM events")) == 0
        assert repository.accept(mapped_candidate())
        before = connection.execute(
            text("SELECT acceptance_key, snapshot FROM event_normalizations")
        ).one()
        command.upgrade(config, "head")
        command.downgrade(config, "0009_mapped_receipts")
        command.upgrade(config, "head")
        assert (
            connection.execute(
                text("SELECT acceptance_key, snapshot FROM event_normalizations")
            ).one()
            == before
        )
