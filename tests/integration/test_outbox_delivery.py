"""Database-clock delivery leases in disposable PostgreSQL databases."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from threading import Barrier

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError

from edgeeagle_domain.sports import EventId
from edgeeagle_ingestion.delivery import DeliveryLeaseLost, DeliveryStatus, OutboxDeliveryRepository
from edgeeagle_ingestion.notifications import EventAccepted
from edgeeagle_persistence.delivery import PostgresOutboxDeliveryRepository
from edgeeagle_persistence.events import PostgresEventAcceptanceRepository
from tests.integration.test_event_acceptance import seed
from tests.integration.test_repositories import repository_engine as repository_engine
from tests.unit.test_event_acceptance import candidate


def enqueue(
    connection: Connection, name: str = "n1", *, occurs_in: timedelta = timedelta(0)
) -> EventAccepted:
    value = candidate()
    now = connection.scalar(text("SELECT clock_timestamp()")) - timedelta(minutes=5)
    value = replace(
        value, raw=replace(value.raw, capture=replace(value.raw.capture, ingested_at=now))
    )
    event_id = replace(value.event.event_id, value=name)
    value = replace(
        value,
        event=replace(value.event, event_id=event_id),
        entries=tuple(replace(entry, event_id=event_id) for entry in value.entries),
        context_version=name,
    )
    message = EventAccepted.for_candidate(
        value,
        event_id=name,
        occurred_at=now + occurs_in,
        correlation_id="workflow",
        causation_id="command",
    )
    PostgresEventAcceptanceRepository(connection).accept_with_notification(value, message)
    return message


def expire(connection: Connection, name: str) -> None:
    # Test-only simulation of a crashed worker, without sleeping or changing the DB clock.
    connection.execute(
        text(
            "UPDATE event_outbox_delivery SET "
            "claimed_at = clock_timestamp() - interval '2 minutes', "
            "lease_expires_at = clock_timestamp() - interval '1 minute' WHERE notification_id = :id"
        ),
        {"id": name},
    )


def test_delivery_claim_acknowledge_and_immutable_intent(repository_engine: Engine) -> None:
    with repository_engine.begin() as connection:
        seed(connection)
        message = enqueue(connection)
        repository: OutboxDeliveryRepository = PostgresOutboxDeliveryRepository(connection)
        assert repository.get("missing") is None
        pending = repository.get(message.event_id)
        assert pending is not None and pending.status is DeliveryStatus.PENDING
        assert pending.attempts == 0
        claim = repository.claim(lease_for=timedelta(minutes=1))
        assert claim is not None and claim.notification == message and claim.attempt == 1
        assert claim.lease_expires_at - claim.claimed_at == timedelta(minutes=1)
        assert repository.claim(lease_for=timedelta(minutes=1)) is None
        with pytest.raises(DeliveryLeaseLost):
            repository.acknowledge(replace(claim, notification=replace(message, event_id="absent")))
    with repository_engine.begin() as connection:
        repository = PostgresOutboxDeliveryRepository(connection)
        repository.acknowledge(claim)
        with pytest.raises(DeliveryLeaseLost):
            repository.acknowledge(claim)
        with pytest.raises(DeliveryLeaseLost):
            repository.retry(claim, retry_after=timedelta(seconds=1))
    with repository_engine.begin() as connection:
        repository = PostgresOutboxDeliveryRepository(connection)
        state = repository.get(message.event_id)
        assert state is not None and state.status is DeliveryStatus.PUBLISHED
        assert state.acknowledged_at is not None
        assert repository.claim(lease_for=timedelta(minutes=1)) is None
        assert (
            PostgresEventAcceptanceRepository(connection).get_notification(
                message.canonical_event_id
            )
            == message
        )


def test_delivery_expired_and_superseded_claims_are_fenced(repository_engine: Engine) -> None:
    with repository_engine.begin() as connection:
        seed(connection)
        enqueue(connection)
        repository = PostgresOutboxDeliveryRepository(connection)
        first = repository.claim(lease_for=timedelta(minutes=1))
        assert first is not None
        expire(connection, first.notification.event_id)
        expired_state = repository.get(first.notification.event_id)
        assert expired_state is not None
        assert expired_state.claimed_at is not None and expired_state.lease_expires_at is not None
        expired_claim = replace(
            first,
            claimed_at=expired_state.claimed_at,
            lease_expires_at=expired_state.lease_expires_at,
        )
        with pytest.raises(DeliveryLeaseLost):
            repository.acknowledge(expired_claim)
        with pytest.raises(DeliveryLeaseLost):
            repository.acknowledge(first)
        with pytest.raises(DeliveryLeaseLost):
            repository.retry(first, retry_after=timedelta(seconds=1))
    with repository_engine.begin() as connection:
        repository = PostgresOutboxDeliveryRepository(connection)
        second = repository.claim(lease_for=timedelta(minutes=1))
        assert second is not None and second.attempt == 2
        assert second.notification == first.notification
        with pytest.raises(DeliveryLeaseLost):
            repository.acknowledge(first)
        repository.acknowledge(second)


def test_delivery_retry_delay_and_outer_rollback(repository_engine: Engine) -> None:
    with repository_engine.begin() as connection:
        seed(connection)
        enqueue(connection)
    with repository_engine.connect() as connection:
        transaction = connection.begin()
        repository = PostgresOutboxDeliveryRepository(connection)
        rolled_back = repository.claim(lease_for=timedelta(minutes=1))
        assert rolled_back is not None
        transaction.rollback()
    with repository_engine.begin() as connection:
        repository = PostgresOutboxDeliveryRepository(connection)
        claim = repository.claim(lease_for=timedelta(minutes=1))
        assert claim is not None and claim.attempt == 1
        with pytest.raises(DeliveryLeaseLost):
            repository.acknowledge(rolled_back)
        repository.retry(claim, retry_after=timedelta(minutes=2))
        state = repository.get(claim.notification.event_id)
        assert state is not None and state.status is DeliveryStatus.PENDING and state.attempts == 1
        assert state.ready_at > claim.claimed_at
        assert repository.claim(lease_for=timedelta(minutes=1)) is None
        with pytest.raises(DeliveryLeaseLost):
            repository.retry(claim, retry_after=timedelta(minutes=2))
        connection.execute(
            text(
                "UPDATE event_outbox_delivery "
                "SET ready_at = clock_timestamp() - interval '1 second'"
            )
        )
        second = repository.claim(lease_for=timedelta(minutes=1))
        assert second is not None and second.attempt == 2


def test_delivery_workers_skip_locked_rows(repository_engine: Engine) -> None:
    with repository_engine.begin() as connection:
        seed(connection)
        enqueue(connection, "n1")
        enqueue(connection, "n2")
    barrier = Barrier(2)

    def claim_one() -> str:
        with repository_engine.begin() as connection:
            connection.execute(text("SET LOCAL statement_timeout = '5s'"))
            result = PostgresOutboxDeliveryRepository(connection).claim(
                lease_for=timedelta(minutes=1)
            )
            assert result is not None
            barrier.wait(timeout=5)  # Hold both row locks until both workers have a claim.
            return result.notification.event_id

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(claim_one) for _ in range(2)]
        assert {future.result() for future in futures} == {"n1", "n2"}


def test_delivery_write_guards(repository_engine: Engine) -> None:
    with repository_engine.connect() as connection:
        with pytest.raises(RuntimeError, match="active"):
            PostgresOutboxDeliveryRepository(connection).claim(lease_for=timedelta(seconds=1))
    for level in ("AUTOCOMMIT", "REPEATABLE READ"):
        with repository_engine.connect().execution_options(isolation_level=level) as connection:
            with connection.begin(), pytest.raises(RuntimeError):
                PostgresOutboxDeliveryRepository(connection).claim(lease_for=timedelta(seconds=1))


def test_delivery_migration_backfill_preserves_intent(repository_engine: Engine) -> None:
    with repository_engine.begin() as connection:
        seed(connection)
        config = Config(str(Path(__file__).parents[2] / "apps/api/alembic.ini"))
        config.attributes["connection"] = connection
        command.downgrade(config, "0006_event_outbox")
        message = enqueue(connection)
        original = connection.scalar(text("SELECT envelope FROM event_outbox"))
        command.upgrade(config, "head")
        repository = PostgresOutboxDeliveryRepository(connection)
        state = repository.get(message.event_id)
        assert state is not None and state.status is DeliveryStatus.PENDING and state.attempts == 0
        assert state.ready_at >= message.occurred_at
        assert connection.scalar(text("SELECT envelope FROM event_outbox")) == original
        assert repository.claim(lease_for=timedelta(seconds=30)) is not None


def test_delivery_does_not_claim_future_occurrence(repository_engine: Engine) -> None:
    with repository_engine.begin() as connection:
        seed(connection)
        message = enqueue(connection, occurs_in=timedelta(days=1))
        repository = PostgresOutboxDeliveryRepository(connection)
        state = repository.get(message.event_id)
        assert state is not None and state.ready_at == message.occurred_at
        assert repository.claim(lease_for=timedelta(seconds=30)) is None


def test_delivery_corrupt_receipt_rolls_back_claim(repository_engine: Engine) -> None:
    with repository_engine.begin() as connection:
        seed(connection)
        message = enqueue(connection)
        connection.execute(text("ALTER TABLE event_normalizations DISABLE TRIGGER USER"))
        connection.execute(text("UPDATE event_normalizations SET acceptance_key = repeat('0', 64)"))
        connection.execute(text("ALTER TABLE event_normalizations ENABLE TRIGGER USER"))
        repository = PostgresOutboxDeliveryRepository(connection)
        with pytest.raises(ValueError):
            repository.claim(lease_for=timedelta(seconds=30))
        state = repository.get(message.event_id)
        assert state is not None and state.status is DeliveryStatus.PENDING and state.attempts == 0
        assert connection.scalar(text("SELECT count(*) FROM sports")) == 1


def test_delivery_acknowledgement_rollback_leaves_recoverable_claim(
    repository_engine: Engine,
) -> None:
    with repository_engine.begin() as connection:
        seed(connection)
        enqueue(connection)
        claim = PostgresOutboxDeliveryRepository(connection).claim(lease_for=timedelta(minutes=1))
        assert claim is not None
    with repository_engine.connect() as connection:
        transaction = connection.begin()
        PostgresOutboxDeliveryRepository(connection).acknowledge(claim)
        transaction.rollback()
    with repository_engine.begin() as connection:
        repository = PostgresOutboxDeliveryRepository(connection)
        state = repository.get(claim.notification.event_id)
        assert state is not None and state.status is DeliveryStatus.LEASED
        repository.acknowledge(claim)


def test_delivery_schema_rejects_invalid_state(repository_engine: Engine) -> None:
    with repository_engine.begin() as connection:
        seed(connection)
        enqueue(connection)
        for assignment in (
            "attempts = -1",
            "status = 'UNKNOWN'",
            "status = 'LEASED'",
            "acknowledged_at = clock_timestamp()",
            "status = 'PUBLISHED'",
        ):
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(text(f"UPDATE event_outbox_delivery SET {assignment}"))
        state = PostgresOutboxDeliveryRepository(connection).get("n1")
        assert state is not None and state.status is DeliveryStatus.PENDING


def test_delivery_missing_intent_read_fails_closed(
    repository_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(self: PostgresEventAcceptanceRepository, event_id: EventId) -> None:
        return None

    with repository_engine.begin() as connection:
        seed(connection)
        enqueue(connection)
        # Fault injection at the reader boundary; never bypass production foreign keys.
        monkeypatch.setattr(PostgresEventAcceptanceRepository, "get_notification", missing)
        repository = PostgresOutboxDeliveryRepository(connection)
        with pytest.raises(ValueError, match="missing"):
            repository.claim(lease_for=timedelta(seconds=30))
        state = repository.get("n1")
        assert state is not None and state.attempts == 0 and state.status is DeliveryStatus.PENDING
