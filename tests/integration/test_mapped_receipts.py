"""Mapped receipt persistence and non-destructive migration rollback gates."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError

from edgeeagle_ingestion.events import EventAcceptanceConflict
from edgeeagle_ingestion.notifications import EventAccepted
from edgeeagle_persistence._event_snapshot import acceptance_key, canonical, encode
from edgeeagle_persistence.consumer import PostgresEventAcceptedHandler
from edgeeagle_persistence.events import PostgresEventAcceptanceRepository
from tests.integration.test_event_acceptance import reidentify, seed
from tests.integration.test_repositories import repository_engine as repository_engine
from tests.unit.test_event_acceptance import candidate
from tests.unit.test_fixture_references import NOW
from tests.unit.test_mapped_receipts import mapped_candidate


def migration_config(connection: Connection) -> Config:
    config = Config(str(Path(__file__).resolve().parents[2] / "apps/api/alembic.ini"))
    config.attributes["connection"] = connection
    return config


def test_mapped_receipt_outbox_and_consumer_use_evidence_identity(
    repository_engine: Engine,
) -> None:
    value = mapped_candidate()
    message = EventAccepted.for_candidate(
        value,
        event_id="mapped-notification",
        occurred_at=NOW,
        correlation_id="mapped-test",
        causation_id="mapped-command",
    )
    assert message.acceptance_key != acceptance_key(candidate())
    with repository_engine.begin() as connection:
        seed(connection)
        repository = PostgresEventAcceptanceRepository(connection)
        assert repository.accept_with_notification(value, message)
    with repository_engine.begin() as connection:
        repository = PostgresEventAcceptanceRepository(connection)
        assert repository.get_notification(value.event.event_id) == message
        assert not repository.accept_with_notification(value, message)
        handler = PostgresEventAcceptedHandler(connection)
        assert handler.handle(message)
        assert not handler.handle(message)
        assert connection.scalar(text("SELECT count(*) FROM event_acceptance_consumptions")) == 1


def test_mapped_receipt_commit_replay_conflict_and_downgrade_guard(
    repository_engine: Engine,
) -> None:
    value = mapped_candidate()
    with repository_engine.begin() as connection:
        seed(connection)
        repository = PostgresEventAcceptanceRepository(connection)
        assert repository.accept(value)
        assert not repository.accept(value)
        assert repository.get(value.event.event_id) == canonical(value)
        assert connection.scalar(text("SELECT snapshot->'format' FROM event_normalizations")) == 2
    with repository_engine.begin() as connection:
        repository = PostgresEventAcceptanceRepository(connection)
        assert not repository.accept(value)
        assert repository.get(value.event.event_id) == canonical(value)
        evidence = value.mapping_evidence
        assert evidence is not None
        changed = replace(value, mapping_evidence=replace(evidence, home_label="Changed guard"))
        for conflicting in (changed, candidate(), reidentify(value)):
            with pytest.raises(EventAcceptanceConflict):
                repository.accept(conflicting)
        with pytest.raises(IntegrityError, match="format-2 receipts"), connection.begin_nested():
            command.downgrade(migration_config(connection), "0008_event_consumption")
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "0010_soccer_receipts"
        )
        assert repository.get(value.event.event_id) == canonical(value)
        assert connection.scalar(text("SELECT count(*) FROM events")) == 1
        for statement in (
            "UPDATE event_normalizations SET snapshot = snapshot",
            "DELETE FROM event_normalizations",
            "TRUNCATE event_normalizations CASCADE",
        ):
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(text(statement))


def test_mapped_receipt_rollback_and_legacy_upgrade_downgrade(repository_engine: Engine) -> None:
    legacy = candidate()
    with repository_engine.begin() as connection:
        seed(connection)
        command.downgrade(migration_config(connection), "0008_event_consumption")
        repository = PostgresEventAcceptanceRepository(connection)
        # Old schema blocks format 2 and acceptance's savepoint removes the event.
        with pytest.raises(IntegrityError):
            repository.accept(mapped_candidate())
        assert connection.scalar(text("SELECT count(*) FROM events")) == 0
        assert repository.accept(legacy)
        before = connection.execute(
            text("SELECT acceptance_key, snapshot FROM event_normalizations")
        ).one()
        command.upgrade(migration_config(connection), "head")
        command.upgrade(migration_config(connection), "head")
        command.downgrade(migration_config(connection), "0008_event_consumption")
        command.upgrade(migration_config(connection), "head")
        after = connection.execute(
            text("SELECT acceptance_key, snapshot FROM event_normalizations")
        ).one()
        assert before == after
        assert before[0] == acceptance_key(legacy)
        assert before[1] == json.loads(encode(legacy))
        assert not repository.accept(legacy)
    with repository_engine.connect() as connection:
        transaction = connection.begin()
        value = reidentify(mapped_candidate())
        assert PostgresEventAcceptanceRepository(connection).accept(value)
        transaction.rollback()
    with repository_engine.begin() as connection:
        assert PostgresEventAcceptanceRepository(connection).get(value.event.event_id) is None
        assert connection.scalar(text("SELECT count(*) FROM event_normalizations")) == 1


@pytest.mark.parametrize("evidence", [None, [], "bad"])
def test_mapped_receipt_schema_rejects_nonobject_evidence(
    repository_engine: Engine, evidence: object
) -> None:
    value = mapped_candidate()
    snapshot = json.loads(encode(value))
    snapshot["candidate"]["mapping_evidence"] = evidence
    with repository_engine.begin() as connection:
        seed(connection)
        from edgeeagle_persistence.sports import PostgresSportsRepository

        PostgresSportsRepository(connection).add_event(value.event, value.entries)
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                text(
                    "INSERT INTO event_normalizations "
                    "(event_id, data_source_id, acceptance_key, snapshot) "
                    "VALUES (:event, :source, :key, CAST(:snapshot AS jsonb))"
                ),
                {
                    "event": value.event.event_id.value,
                    "source": value.provider_key.data_source_id.value,
                    "key": acceptance_key(value),
                    "snapshot": json.dumps(snapshot),
                },
            )
