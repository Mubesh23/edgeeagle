"""PostgreSQL initial acceptance, receipts, replay, and savepoint semantics."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta, timezone
from threading import Barrier

import pytest
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import IntegrityError, NotSupportedError

from edgeeagle_domain.sports import EventId
from edgeeagle_ingestion.events import (
    EventAcceptanceConflict,
    EventAcceptanceRepository,
    EventCandidate,
)
from edgeeagle_persistence._event_snapshot import acceptance_key, canonical, encode
from edgeeagle_persistence.events import PostgresEventAcceptanceRepository
from edgeeagle_persistence.provenance import PostgresDataSourceRepository
from edgeeagle_persistence.sports import PostgresSportsRepository
from tests.integration.test_repositories import repository_engine as repository_engine
from tests.integration.test_repositories import source
from tests.unit.test_event_acceptance import candidate
from tests.unit.test_event_normalization import binding


def seed(connection: Connection, *, include_source: bool = True) -> None:
    context = binding()
    if include_source:
        PostgresDataSourceRepository(connection).add(source(context.key.data_source_id.value))
    sports = PostgresSportsRepository(connection)
    sports.add_sport(context.sport)
    sports.add_competition(context.competition)
    sports.add_season(context.season)
    sports.add_participant(context.home)
    sports.add_participant(context.away)


def reidentify(value: EventCandidate) -> EventCandidate:
    return replace(
        value,
        event=replace(value.event, event_id=EventId("other")),
        entries=tuple(replace(entry, event_id=EventId("other")) for entry in value.entries),
    )


def test_event_acceptance_commit_and_replay(repository_engine: Engine) -> None:
    value = candidate()
    with repository_engine.begin() as connection:
        seed(connection)
        repository: EventAcceptanceRepository = PostgresEventAcceptanceRepository(connection)
        assert repository.get(value.event.event_id) is None
        assert repository.accept(value) is True
        assert repository.accept(replace(value, entries=tuple(reversed(value.entries)))) is False
        assert (
            repository.accept(
                replace(
                    value,
                    event=replace(
                        value.event,
                        starts_at=value.event.starts_at.astimezone(timezone(timedelta(hours=-5))),
                    ),
                )
            )
            is False
        )
        assert repository.get(value.event.event_id) == canonical(value)
        with repository_engine.begin() as reader:
            assert PostgresEventAcceptanceRepository(reader).get(value.event.event_id) is None
    with repository_engine.begin() as connection:
        repository = PostgresEventAcceptanceRepository(connection)
        assert repository.get(value.event.event_id) == canonical(value)
        assert repository.accept(value) is False
        assert connection.scalar(text("SELECT count(*) FROM event_normalizations")) == 1
        assert PostgresSportsRepository(connection).get_event(value.event.event_id) == value.event


def test_event_acceptance_conflicts_leave_original_intact(repository_engine: Engine) -> None:
    value = candidate()
    with repository_engine.begin() as connection:
        seed(connection)
        repository = PostgresEventAcceptanceRepository(connection)
        assert repository.accept(value)
        variants = [
            replace(value, event=replace(value.event, status="FINAL")),
            replace(value, entries=(replace(value.entries[0], role="OTHER"), value.entries[1])),
            replace(value, raw=replace(value.raw, sha256="0" * 64)),
            replace(value, parser_version="v2"),
            replace(value, normalizer_version="v2"),
            replace(value, context_version="v2"),
            replace(value, provider_key=replace(value.provider_key, provider_entity_id="other")),
            reidentify(value),
        ]
        for variant in variants:
            with pytest.raises(EventAcceptanceConflict):
                repository.accept(variant)
            assert repository.get(value.event.event_id) == canonical(value)
            assert connection.scalar(text("SELECT count(*) FROM events")) == 1
            assert connection.scalar(text("SELECT count(*) FROM event_participants")) == 2
            assert connection.scalar(text("SELECT count(*) FROM event_normalizations")) == 1


def test_event_acceptance_receipt_failure_and_outer_rollback(repository_engine: Engine) -> None:
    value = candidate()
    with repository_engine.begin() as connection:
        seed(connection, include_source=False)
        repository = PostgresEventAcceptanceRepository(connection)
        with pytest.raises(IntegrityError):
            repository.accept(value)
        assert connection.scalar(text("SELECT count(*) FROM events")) == 0
        assert connection.scalar(text("SELECT count(*) FROM event_participants")) == 0
        assert connection.scalar(text("SELECT count(*) FROM sports")) == 1
        PostgresDataSourceRepository(connection).add(source(value.raw.capture.data_source_id.value))
    with repository_engine.connect() as connection:
        transaction = connection.begin()
        assert PostgresEventAcceptanceRepository(connection).accept(value)
        transaction.rollback()
    with repository_engine.begin() as connection:
        assert connection.scalar(text("SELECT count(*) FROM events")) == 0
        assert connection.scalar(text("SELECT count(*) FROM event_participants")) == 0
        assert connection.scalar(text("SELECT count(*) FROM event_normalizations")) == 0


def test_event_acceptance_requires_references_and_receipt(repository_engine: Engine) -> None:
    value = candidate()
    with repository_engine.begin() as connection:
        repository = PostgresEventAcceptanceRepository(connection)
        with pytest.raises(ValueError, match="missing"):
            repository.accept(value)
        seed(connection)
        sports = PostgresSportsRepository(connection)
        sports.add_event(value.event, value.entries)
        with pytest.raises(EventAcceptanceConflict):
            repository.accept(value)
        assert repository.get(value.event.event_id) is None


@pytest.mark.parametrize("mode", ["exact", "changed", "identity"])
def test_event_acceptance_concurrent_writers(repository_engine: Engine, mode: str) -> None:
    first = candidate()
    second = first
    if mode == "changed":
        second = replace(first, parser_version="v2")
    elif mode == "identity":
        second = reidentify(first)
    with repository_engine.begin() as connection:
        seed(connection)
    barrier = Barrier(2)

    def accept(value: EventCandidate) -> bool | str:
        with repository_engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text("SET LOCAL statement_timeout = '10s'"))
            barrier.wait(timeout=5)
            try:
                return PostgresEventAcceptanceRepository(connection).accept(value)
            except EventAcceptanceConflict:
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(accept, (first, second)))
    assert results.count(True) == 1
    assert results.count(False if mode == "exact" else "conflict") == 1
    with repository_engine.begin() as connection:
        assert connection.scalar(text("SELECT count(*) FROM events")) == 1
        assert connection.scalar(text("SELECT count(*) FROM event_participants")) == 2
        assert connection.scalar(text("SELECT count(*) FROM event_normalizations")) == 1


def test_event_acceptance_transaction_guards(repository_engine: Engine) -> None:
    with repository_engine.connect() as connection:
        with pytest.raises(RuntimeError, match="active"):
            PostgresEventAcceptanceRepository(connection).accept(candidate())
    for level in ("AUTOCOMMIT", "REPEATABLE READ"):
        with repository_engine.connect().execution_options(isolation_level=level) as connection:
            with connection.begin(), pytest.raises(RuntimeError):
                PostgresEventAcceptanceRepository(connection).accept(candidate())


def test_event_acceptance_immutable_receipt_and_current_drift(repository_engine: Engine) -> None:
    value = candidate()
    with repository_engine.begin() as connection:
        seed(connection)
        repository = PostgresEventAcceptanceRepository(connection)
        repository.accept(value)
        for statement in (
            "UPDATE event_normalizations SET acceptance_key = acceptance_key",
            "DELETE FROM event_normalizations",
            "TRUNCATE event_normalizations, event_outbox",
        ):
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(text(statement))
        # PostgreSQL rejects parent-only TRUNCATE before invoking immutable triggers.
        with pytest.raises(NotSupportedError), connection.begin_nested():
            connection.execute(text("TRUNCATE event_normalizations"))
        connection.execute(text("UPDATE events SET status = 'FINAL'"))
        assert repository.get(value.event.event_id) == canonical(value)
        with pytest.raises(EventAcceptanceConflict):
            repository.accept(value)


def test_event_acceptance_corrupt_receipt_fails_closed(repository_engine: Engine) -> None:
    value = candidate()
    with repository_engine.begin() as connection:
        seed(connection)
        repository = PostgresEventAcceptanceRepository(connection)
        repository.accept(value)
        # Owner-only bypass solely within this disposable test database.
        connection.execute(text("ALTER TABLE event_normalizations DISABLE TRIGGER USER"))
        connection.execute(text("UPDATE event_normalizations SET acceptance_key = repeat('0', 64)"))
        connection.execute(text("ALTER TABLE event_normalizations ENABLE TRIGGER USER"))
        with pytest.raises(ValueError, match="identity"):
            repository.get(value.event.event_id)
        with pytest.raises(ValueError, match="identity"):
            repository.accept(value)


def test_event_acceptance_schema_identity_checks(repository_engine: Engine) -> None:
    value = candidate()
    with repository_engine.begin() as connection:
        seed(connection)
        PostgresSportsRepository(connection).add_event(value.event, value.entries)
        statement = text(
            "INSERT INTO event_normalizations (event_id, data_source_id, acceptance_key, snapshot) "
            "VALUES (:event, :source, :key, CAST(:snapshot AS jsonb))"
        )
        fields = {
            "event": value.event.event_id.value,
            "source": value.raw.capture.data_source_id.value,
            "key": acceptance_key(value),
            "snapshot": encode(value),
        }
        for change in (
            {"snapshot": "{}"},
            {"snapshot": '{"format":1,"candidate":{}}'},
            {"snapshot": encode(reidentify(value))},
            {"source": "other"},
            {"key": "invalid-digest"},
        ):
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(statement, fields | change)
        assert connection.scalar(text("SELECT count(*) FROM event_normalizations")) == 0
        connection.execute(statement, fields)
        assert PostgresEventAcceptanceRepository(connection).get(value.event.event_id) == canonical(
            value
        )
