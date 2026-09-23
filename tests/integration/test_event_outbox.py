"""Atomic PostgreSQL publication intent, without an AWS publisher."""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from threading import Barrier

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from edgeeagle_ingestion.events import EventAcceptanceConflict
from edgeeagle_ingestion.notifications import EventAccepted, EventPublicationRepository
from edgeeagle_persistence.events import PostgresEventAcceptanceRepository
from tests.integration.test_event_acceptance import reidentify, seed
from tests.integration.test_repositories import repository_engine as repository_engine
from tests.unit.test_event_acceptance import candidate
from tests.unit.test_event_notifications import notification


def test_outbox_commit_visibility_and_exact_replay(repository_engine: Engine) -> None:
    value, message = candidate(), notification()
    with repository_engine.begin() as connection:
        seed(connection)
        repository: EventPublicationRepository = PostgresEventAcceptanceRepository(connection)
        assert repository.get_notification(value.event.event_id) is None
        assert repository.accept_with_notification(value, message) is True
        assert repository.accept_with_notification(value, message) is False
        assert repository.get_notification(value.event.event_id) == message
        with repository_engine.begin() as reader:
            assert (
                PostgresEventAcceptanceRepository(reader).get_notification(value.event.event_id)
                is None
            )
    with repository_engine.begin() as connection:
        repository = PostgresEventAcceptanceRepository(connection)
        assert repository.get_notification(value.event.event_id) == message
        assert repository.accept_with_notification(value, message) is False
        assert connection.scalar(text("SELECT count(*) FROM event_outbox")) == 1


def test_outbox_conflicting_metadata_and_legacy_receipts(repository_engine: Engine) -> None:
    value, message = candidate(), notification()
    with repository_engine.begin() as connection:
        seed(connection)
        repository = PostgresEventAcceptanceRepository(connection)
        repository.accept(value)
        with pytest.raises(EventAcceptanceConflict):
            repository.accept_with_notification(value, message)
        assert connection.scalar(text("SELECT count(*) FROM event_outbox")) == 0
    # A legacy row is not silently assigned invented publication metadata.
    with repository_engine.begin() as connection:
        repository = PostgresEventAcceptanceRepository(connection)
        assert repository.accept(value) is False


def test_outbox_collision_rolls_back_new_event_and_receipt(repository_engine: Engine) -> None:
    value, message = candidate(), notification()
    other = replace(reidentify(value), context_version="other-context")
    collision = EventAccepted.for_candidate(
        other,
        event_id=message.event_id,
        occurred_at=message.occurred_at,
        correlation_id=message.correlation_id,
        causation_id=message.causation_id,
    )
    with repository_engine.begin() as connection:
        seed(connection)
        repository = PostgresEventAcceptanceRepository(connection)
        repository.accept_with_notification(value, message)
        for changed in (
            replace(message, event_id="other"),
            replace(message, correlation_id="other"),
            replace(message, causation_id="other"),
            replace(message, occurred_at=message.occurred_at + timedelta(seconds=1)),
        ):
            with pytest.raises(EventAcceptanceConflict):
                repository.accept_with_notification(value, changed)
        with pytest.raises(EventAcceptanceConflict):
            repository.accept_with_notification(other, collision)
        assert repository.get(other.event.event_id) is None
        for table in ("events", "event_normalizations", "event_outbox"):
            assert connection.scalar(text(f"SELECT count(*) FROM {table}")) == 1
        assert connection.scalar(text("SELECT count(*) FROM event_participants")) == 2
        assert repository.accept_with_notification(other, replace(collision, event_id="second"))


def test_outbox_outer_rollback_and_metadata_validation(repository_engine: Engine) -> None:
    value, message = candidate(), notification()
    with repository_engine.begin() as connection:
        seed(connection)
    with repository_engine.connect() as connection:
        with pytest.raises(RuntimeError):
            PostgresEventAcceptanceRepository(connection).accept_with_notification(value, message)
        transaction = connection.begin()
        repository = PostgresEventAcceptanceRepository(connection)
        for changed in (
            replace(message, acceptance_key="0" * 64),
            replace(message, canonical_event_id=reidentify(value).event.event_id),
            replace(message, occurred_at=value.raw.capture.ingested_at.replace(year=2000)),
        ):
            with pytest.raises(ValueError):
                repository.accept_with_notification(value, changed)
        assert repository.accept_with_notification(value, message)
        transaction.rollback()
    with repository_engine.begin() as connection:
        for table in ("events", "event_participants", "event_normalizations", "event_outbox"):
            assert connection.scalar(text(f"SELECT count(*) FROM {table}")) == 0


@pytest.mark.parametrize("conflict", [False, True])
def test_outbox_concurrent_replays(repository_engine: Engine, conflict: bool) -> None:
    value, message = candidate(), notification()
    with repository_engine.begin() as connection:
        seed(connection)
    barrier = Barrier(2)

    def accept(envelope: EventAccepted) -> bool | str:
        with repository_engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text("SET LOCAL statement_timeout = '10s'"))
            barrier.wait(timeout=5)
            try:
                return PostgresEventAcceptanceRepository(connection).accept_with_notification(
                    value, envelope
                )
            except EventAcceptanceConflict:
                return "conflict"

    second = replace(message, correlation_id="other") if conflict else message
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(accept, (message, second)))
    assert results.count(True) == 1
    assert results.count("conflict" if conflict else False) == 1
    with repository_engine.begin() as connection:
        assert connection.scalar(text("SELECT count(*) FROM event_outbox")) == 1


def test_outbox_immutable_and_corruption_detection(repository_engine: Engine) -> None:
    value, message = candidate(), notification()
    with repository_engine.begin() as connection:
        seed(connection)
        repository = PostgresEventAcceptanceRepository(connection)
        repository.accept_with_notification(value, message)
        for statement in (
            "UPDATE event_outbox SET envelope = envelope",
            "DELETE FROM event_outbox",
            "TRUNCATE event_outbox",
        ):
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(text(statement))
        connection.execute(text("ALTER TABLE event_outbox DISABLE TRIGGER USER"))
        connection.execute(
            text(
                "UPDATE event_outbox SET envelope = jsonb_set(envelope, "
                "'{payload,acceptance_key}', to_jsonb(repeat('0', 64)))"
            )
        )
        connection.execute(text("ALTER TABLE event_outbox ENABLE TRIGGER USER"))
        with pytest.raises(ValueError):
            repository.get_notification(value.event.event_id)
        with pytest.raises(ValueError):
            repository.accept_with_notification(value, message)


def test_outbox_schema_constraints_and_migration_preserve_receipts(
    repository_engine: Engine,
) -> None:
    value, message = candidate(), notification()
    with repository_engine.begin() as connection:
        seed(connection)
        repository = PostgresEventAcceptanceRepository(connection)
        repository.accept(value)
        config = Config(str(Path(__file__).parents[2] / "apps/api/alembic.ini"))
        config.attributes["connection"] = connection
        command.downgrade(config, "0005_event_acceptance")
        assert repository.get(value.event.event_id) is not None
        command.upgrade(config, "head")
        assert repository.get(value.event.event_id) is not None
        assert repository.get_notification(value.event.event_id) is None
        statement = text(
            "INSERT INTO event_outbox (notification_id, canonical_event_id, envelope) "
            "VALUES (:notification, :event, CAST(:envelope AS jsonb))"
        )
        for envelope in (
            {},
            message.to_envelope() | {"published_at": message.occurred_at.isoformat()},
            message.to_envelope() | {"version": 2},
            message.to_envelope() | {"event_id": "mismatched"},
        ):
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    statement,
                    {
                        "notification": message.event_id,
                        "event": value.event.event_id.value,
                        "envelope": json.dumps(envelope),
                    },
                )
        missing = replace(message, canonical_event_id=reidentify(value).event.event_id)
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                statement,
                {
                    "notification": missing.event_id,
                    "event": missing.canonical_event_id.value,
                    "envelope": json.dumps(missing.to_envelope()),
                },
            )
        assert connection.scalar(text("SELECT count(*) FROM event_outbox")) == 0
