"""Atomic Sportmonks receipt acceptance against disposable PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from threading import Barrier, Event

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from edgeeagle_domain.mappings import MappingStatus
from edgeeagle_domain.sports import EventId
from edgeeagle_ingestion.sportmonks_acceptance import SportmonksReceiptConflict
from edgeeagle_ingestion.sportmonks_normalization import NormalizedSportmonksFixture
from edgeeagle_ingestion.sportmonks_receipts import sportmonks_capture_identity
from edgeeagle_persistence.mappings import PostgresMappingRepository
from edgeeagle_persistence.sportmonks_receipts import PostgresSportmonksReceiptRepository
from edgeeagle_persistence.sports import PostgresSportsRepository
from tests.integration.test_repositories import repository_engine as repository_engine
from tests.integration.test_sportmonks_references import seed
from tests.unit.test_sportmonks_receipts import capture


def test_sportmonks_acceptance_is_atomic_idempotent_and_conflict_safe(
    repository_engine: Engine,
) -> None:
    value, _ = capture()
    identity = sportmonks_capture_identity(value)
    with repository_engine.begin() as connection:
        seed(connection, value.references)
        repository = PostgresSportmonksReceiptRepository(connection)
        assert repository.accept(value) == 1
        assert repository.accept(value) == 0
        assert repository.get(identity) == value

        changed_context = replace(
            value.references.context,
            home=replace(value.references.context.home, canonical_name="Changed evidence"),
        )
        changed = replace(
            value,
            references=replace(value.references, context=changed_context),
        )
        assert sportmonks_capture_identity(changed) == identity
        with pytest.raises(SportmonksReceiptConflict):
            repository.accept(changed)

        # Exact retry and get remain evidence reads after canonical/mapping changes.
        connection.execute(text("UPDATE events SET status = 'FINAL'"))
        event_revision = value.references.event_revision
        later = event_revision.available_at + timedelta(seconds=1)
        PostgresMappingRepository(connection).append(
            replace(
                event_revision,
                revision=2,
                status=MappingStatus.REVOKED,
                validated_at=later,
                available_at=later,
                ingested_at=later,
            )
        )
        assert repository.get(identity) == value
        assert repository.accept(value) == 0
        assert connection.scalar(text("SELECT count(*) FROM sportmonks_capture_receipts")) == 1
        assert connection.scalar(text("SELECT count(*) FROM events")) == 1
        assert connection.scalar(text("SELECT count(*) FROM provider_mapping_revisions")) == 7
        assert connection.scalar(text("SELECT count(*) FROM event_outbox")) == 0


def test_sportmonks_acceptance_rejects_current_canonical_drift(repository_engine: Engine) -> None:
    value, _ = capture()
    with repository_engine.begin() as connection:
        seed(connection, value.references)
        connection.execute(text("UPDATE participants SET canonical_name = 'Changed now'"))
        with pytest.raises(SportmonksReceiptConflict, match="canonical"):
            PostgresSportmonksReceiptRepository(connection).accept(value)
        assert connection.scalar(text("SELECT count(*) FROM sportmonks_capture_receipts")) == 0
        assert connection.scalar(text("SELECT count(*) FROM events")) == 1
        assert connection.scalar(text("SELECT count(*) FROM provider_mapping_revisions")) == 6
        assert connection.scalar(text("SELECT count(*) FROM event_outbox")) == 0


def test_sportmonks_acceptance_savepoint_and_outer_rollback(repository_engine: Engine) -> None:
    value, _ = capture()
    with repository_engine.begin() as connection:
        seed(connection, value.references)
        repository = PostgresSportmonksReceiptRepository(connection)
        original_get = repository.get
        calls = 0

        def missing_readback(capture_id: str) -> NormalizedSportmonksFixture | None:
            nonlocal calls
            calls += 1
            if calls == 2:
                return None
            return original_get(capture_id)

        repository.get = missing_readback  # type: ignore[method-assign]
        with pytest.raises(SportmonksReceiptConflict, match="readback"):
            repository.accept(value)
        assert connection.scalar(text("SELECT count(*) FROM sportmonks_capture_receipts")) == 0

    with repository_engine.connect() as connection:
        transaction = connection.begin()
        assert PostgresSportmonksReceiptRepository(connection).accept(value) == 1
        transaction.rollback()
    with repository_engine.begin() as connection:
        assert (
            PostgresSportmonksReceiptRepository(connection).get(sportmonks_capture_identity(value))
            is None
        )


@pytest.mark.parametrize("conflicting", [False, True])
def test_sportmonks_acceptance_first_writer_race(
    repository_engine: Engine, conflicting: bool
) -> None:
    value, _ = capture()
    with repository_engine.begin() as connection:
        seed(connection, value.references)
        if conflicting:
            references = value.references
            other_event = replace(references.event, event_id=EventId("alternate-event"))
            other_entries = tuple(
                replace(entry, event_id=other_event.event_id) for entry in references.entries
            )
            PostgresSportsRepository(connection).add_event(other_event, other_entries)
            old_revision = references.event_revision
            available = old_revision.available_at + timedelta(days=1)
            PostgresMappingRepository(connection).append(
                replace(
                    old_revision,
                    revision=2,
                    canonical_entity_id=other_event.event_id,
                    validated_at=available,
                    available_at=available,
                    ingested_at=available,
                )
            )
            changed_references = replace(
                references,
                context=replace(references.context, as_of=available),
                event=other_event,
                entries=other_entries,
                event_revision=replace(
                    old_revision,
                    revision=2,
                    canonical_entity_id=other_event.event_id,
                    validated_at=available,
                    available_at=available,
                    ingested_at=available,
                ),
            )
            changed_value = replace(value, references=changed_references)
        else:
            changed_value = value
    assert sportmonks_capture_identity(changed_value) == sportmonks_capture_identity(value)
    barrier = Barrier(2)

    def accept(receipt: NormalizedSportmonksFixture) -> int:
        with repository_engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text("SET LOCAL statement_timeout = '10s'"))
            barrier.wait(timeout=5)
            try:
                return PostgresSportmonksReceiptRepository(connection).accept(receipt)
            except SportmonksReceiptConflict:
                return -1

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(accept, (value, changed_value)))
    assert sorted(results) == ([-1, 1] if conflicting else [0, 1])
    with repository_engine.begin() as connection:
        assert connection.scalar(text("SELECT count(*) FROM sportmonks_capture_receipts")) == 1
        assert connection.scalar(text("SELECT count(*) FROM event_outbox")) == 0


def test_sportmonks_acceptance_locks_context_until_caller_commit(
    repository_engine: Engine,
) -> None:
    value, _ = capture()
    with repository_engine.begin() as connection:
        seed(connection, value.references)

    accepted = Event()
    release = Event()
    update_started = Event()

    def accept_and_hold() -> None:
        with repository_engine.connect() as connection:
            transaction = connection.begin()
            assert PostgresSportmonksReceiptRepository(connection).accept(value) == 1
            accepted.set()
            assert release.wait(timeout=5)
            transaction.commit()

    def competing_update() -> None:
        assert accepted.wait(timeout=5)
        with repository_engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout = '100ms'"))
            update_started.set()
            connection.execute(text("UPDATE participants SET canonical_name = 'Racing update'"))

    with ThreadPoolExecutor(max_workers=2) as pool:
        acceptance = pool.submit(accept_and_hold)
        update = pool.submit(competing_update)
        assert update_started.wait(timeout=5)
        with pytest.raises(DBAPIError, match="lock timeout"):
            update.result(timeout=5)
        release.set()
        acceptance.result(timeout=5)

    with repository_engine.begin() as connection:
        connection.execute(text("UPDATE participants SET canonical_name = 'Racing update'"))
        assert connection.scalar(text("SELECT count(*) FROM sportmonks_capture_receipts")) == 1


def test_sportmonks_acceptance_propagates_bounded_lock_failure(
    repository_engine: Engine,
) -> None:
    value, _ = capture()
    with repository_engine.begin() as connection:
        seed(connection, value.references)

    with repository_engine.connect() as blocker:
        blocker_transaction = blocker.begin()
        blocker.execute(
            text("SELECT participant_id FROM participants WHERE participant_id = :id FOR UPDATE"),
            {"id": value.references.context.home.participant_id.value},
        )
        with repository_engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout = '100ms'"))
            with pytest.raises(DBAPIError, match="lock timeout"):
                PostgresSportmonksReceiptRepository(connection).accept(value)
            assert connection.scalar(text("SELECT count(*) FROM sportmonks_capture_receipts")) == 0
        blocker_transaction.rollback()


def test_sportmonks_acceptance_requires_caller_owned_read_committed_transaction(
    repository_engine: Engine,
) -> None:
    value, _ = capture()
    with repository_engine.connect() as connection:
        with pytest.raises(RuntimeError, match="active"):
            PostgresSportmonksReceiptRepository(connection).accept(value)
    with repository_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        with connection.begin(), pytest.raises(RuntimeError, match="Autocommit"):
            PostgresSportmonksReceiptRepository(connection).accept(value)
    with repository_engine.connect().execution_options(
        isolation_level="REPEATABLE READ"
    ) as connection:
        with connection.begin(), pytest.raises(ValueError, match="READ COMMITTED"):
            PostgresSportmonksReceiptRepository(connection).accept(value)
