"""Mapping history, replay, and concurrency against disposable PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from threading import Barrier

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from edgeeagle_domain.mapping_repository import MappingConflictError, MappingRepository
from edgeeagle_domain.mappings import (
    CanonicalEntityId,
    MappingStatus,
    ProviderEntityKey,
    ProviderMappingRevision,
)
from edgeeagle_domain.provenance import DataSourceId, VenueId
from edgeeagle_domain.sports import CompetitionId, EventId, ParticipantId, SeasonId, SportId
from edgeeagle_persistence.mappings import PostgresMappingRepository
from tests.integration.test_mapping_schema import add_key, add_revision, seed_targets
from tests.integration.test_repositories import repository_engine as repository_engine

KEY = ProviderEntityKey(
    data_source_id=DataSourceId("same-id"),
    provider_entity_type="fixture",
    provider_entity_id="provider-id",
)
TIME = datetime(2026, 1, 1, tzinfo=UTC)


def decision(number: int = 1) -> ProviderMappingRevision:
    return ProviderMappingRevision(
        key=KEY,
        revision=number,
        canonical_entity_id=SportId("s"),
        mapping_method="fixture",
        confidence=Decimal("0.123456789123456789"),
        validated_by="fixture-reviewer",
        validated_at=TIME,
        available_at=TIME + timedelta(days=number),
        ingested_at=TIME + timedelta(days=number),
        status=MappingStatus.MAPPED,
    )


def test_mapping_repository_history_replay_and_resolution(repository_engine: Engine) -> None:
    first = decision()
    revoked = replace(decision(2), status=MappingStatus.REVOKED)
    restored = decision(3)
    with repository_engine.begin() as connection:
        seed_targets(connection)
        repository: MappingRepository = PostgresMappingRepository(connection)
        assert repository.history(KEY) == ()
        assert repository.resolve(KEY, as_of=TIME) is None
        assert repository.append(first) == first
        assert repository.append(revoked) == revoked
        assert repository.append(restored) == restored
        assert repository.append(first) == first  # Old replay does not move the head.
        assert repository.history(KEY) == (first, revoked, restored)
        assert repository.resolve(KEY, as_of=TIME) is None
        assert repository.resolve(KEY, as_of=first.available_at) == first
        assert repository.resolve(KEY, as_of=revoked.available_at) is None
        assert repository.resolve(KEY, as_of=restored.available_at) == restored
        with repository_engine.begin() as other:
            assert PostgresMappingRepository(other).history(KEY) == ()
    with repository_engine.begin() as connection:
        assert PostgresMappingRepository(connection).history(KEY) == (first, revoked, restored)


@pytest.mark.parametrize(
    "target",
    [
        SportId("s"),
        CompetitionId("c"),
        SeasonId("season"),
        ParticipantId("p00"),
        EventId("e"),
        VenueId("same-id"),
    ],
)
def test_mapping_repository_typed_targets(
    repository_engine: Engine, target: CanonicalEntityId
) -> None:
    with repository_engine.begin() as connection:
        seed_targets(connection)
        repository = PostgresMappingRepository(connection)
        row = replace(decision(), canonical_entity_id=target)
        assert repository.append(row) == row
        assert repository.history(KEY) == (row,)


def test_mapping_repository_conflicts_and_invalid_history(repository_engine: Engine) -> None:
    with repository_engine.begin() as connection:
        seed_targets(connection)
        repository = PostgresMappingRepository(connection)
        first = decision()
        repository.append(first)
        for conflicting in (
            replace(first, mapping_method="changed"),
            replace(first, confidence=None),
            replace(first, validated_by="other"),
            replace(first, validated_at=TIME - timedelta(days=1)),
            replace(first, ingested_at=TIME + timedelta(days=3)),
            replace(first, available_at=TIME),
            replace(first, canonical_entity_id=SportId("other")),
            replace(first, status=MappingStatus.REVOKED),
            decision(3),
        ):
            with pytest.raises(MappingConflictError):
                repository.append(conflicting)
        for invalid in (
            replace(decision(2), canonical_entity_id=VenueId("same-id")),
            replace(decision(2), available_at=TIME),
            replace(decision(2), available_at=TIME, ingested_at=TIME),
            replace(
                decision(2), status=MappingStatus.REVOKED, canonical_entity_id=SportId("other")
            ),
        ):
            with pytest.raises(ValueError):
                repository.append(invalid)
        assert repository.history(KEY) == (first,)
        assert repository.append(decision(2)) == decision(2)


def test_mapping_repository_savepoint_and_outer_rollback(repository_engine: Engine) -> None:
    with repository_engine.begin() as connection:
        seed_targets(connection)
    with pytest.raises(RuntimeError, match="abort"), repository_engine.begin() as connection:
        repository = PostgresMappingRepository(connection)
        with pytest.raises(IntegrityError):
            repository.append(replace(decision(), canonical_entity_id=SportId("missing")))
        assert connection.scalar(text("SELECT count(*) FROM provider_mapping_keys")) == 0
        with pytest.raises(ValueError):
            repository.append(replace(decision(), status=MappingStatus.REVOKED))
        assert connection.scalar(text("SELECT count(*) FROM provider_mapping_keys")) == 0
        repository.append(decision())
        raise RuntimeError("abort")
    with repository_engine.begin() as connection:
        assert PostgresMappingRepository(connection).history(KEY) == ()
        assert connection.scalar(text("SELECT count(*) FROM provider_mapping_keys")) == 0


def test_mapping_repository_equivalent_instants_are_replays(repository_engine: Engine) -> None:
    row = decision()
    offset = timezone(timedelta(hours=3))
    shifted = replace(
        row,
        validated_at=row.validated_at.astimezone(offset),
        available_at=row.available_at.astimezone(offset),
        ingested_at=row.ingested_at.astimezone(offset),
    )
    with repository_engine.begin() as connection:
        seed_targets(connection)
        repository = PostgresMappingRepository(connection)
        repository.append(row)
        assert repository.append(shifted) == row
        assert len(repository.history(KEY)) == 1


def test_mapping_repository_rejects_corrupt_future_history(repository_engine: Engine) -> None:
    key = replace(KEY, provider_entity_type="entity", provider_entity_id="SPORT")
    with repository_engine.begin() as connection:
        seed_targets(connection)
        add_key(connection)
        add_revision(connection)
        # Legal per-row SQL, illegal inter-revision chronology; never hide future corruption.
        add_revision(
            connection,
            revision=2,
            validated_at=TIME - timedelta(days=1),
            available_at=TIME - timedelta(days=1),
            ingested_at=TIME - timedelta(days=1),
        )
        repository = PostgresMappingRepository(connection)
        with pytest.raises(ValueError, match="must not decrease"):
            repository.resolve(key, as_of=TIME - timedelta(days=2))
        with pytest.raises(ValueError, match="must not decrease"):
            repository.append(replace(decision(3), key=key))
        with pytest.raises(ValueError, match="must not decrease"):
            repository.append(replace(decision(), key=key, available_at=TIME, ingested_at=TIME))


def test_mapping_repository_snapshot_and_write_isolation(repository_engine: Engine) -> None:
    with repository_engine.begin() as connection:
        seed_targets(connection)
        PostgresMappingRepository(connection).append(decision())
    with repository_engine.connect().execution_options(isolation_level="REPEATABLE READ") as reader:
        with reader.begin():
            repository = PostgresMappingRepository(reader)
            assert repository.history(KEY) == (decision(),)
            with pytest.raises(ValueError, match="READ COMMITTED"):
                repository.append(decision(2))
            with repository_engine.begin() as writer:
                PostgresMappingRepository(writer).append(decision(2))
            assert repository.history(KEY) == (decision(),)
            assert repository.resolve(KEY, as_of=TIME + timedelta(days=10)) == decision()
    with repository_engine.begin() as connection:
        assert len(PostgresMappingRepository(connection).history(KEY)) == 2
    with repository_engine.connect() as connection:
        repository = PostgresMappingRepository(connection)
        with pytest.raises(RuntimeError, match="active caller-owned"):
            repository.append(decision())
        with pytest.raises(RuntimeError, match="active caller-owned"):
            repository.history(KEY)
        connection.execution_options(isolation_level="AUTOCOMMIT")
        with connection.begin(), pytest.raises(RuntimeError, match="Autocommit"):
            repository.append(decision())


def test_mapping_repository_correction_revocation_and_namespaces(repository_engine: Engine) -> None:
    with repository_engine.begin() as connection:
        seed_targets(connection)
        repository = PostgresMappingRepository(connection)
        first = replace(decision(), canonical_entity_id=ParticipantId("p00"))
        second = replace(decision(2), canonical_entity_id=ParticipantId("p01"))
        third = replace(
            decision(3), canonical_entity_id=ParticipantId("p01"), status=MappingStatus.REVOKED
        )
        for row in (first, second, third):
            repository.append(row)
        assert repository.resolve(KEY, as_of=second.available_at) == second
        assert repository.resolve(KEY, as_of=third.available_at) is None
        assert repository.append(first) == first
        other_key = replace(KEY, provider_entity_type="other")
        independent = replace(decision(), key=other_key)
        repository.append(independent)
        assert repository.history(other_key) == (independent,)
        assert repository.history(KEY) == (first, second, third)


def test_mapping_repository_ingestion_time_cannot_decrease(repository_engine: Engine) -> None:
    with repository_engine.begin() as connection:
        seed_targets(connection)
        repository = PostgresMappingRepository(connection)
        first = replace(decision(), ingested_at=TIME + timedelta(days=5))
        repository.append(first)
        with pytest.raises(ValueError, match="ingested_at must not decrease"):
            repository.append(decision(2))
        assert repository.history(KEY) == (first,)


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("same_payload", [False, True])
def test_mapping_repository_concurrent_append(
    repository_engine: Engine,
    existing: bool,
    same_payload: bool,
) -> None:
    with repository_engine.begin() as connection:
        seed_targets(connection)
        if existing:
            PostgresMappingRepository(connection).append(decision())
    row = decision(2 if existing else 1)
    competing = row if same_payload else replace(row, mapping_method="competing")
    barrier = Barrier(2)

    def append(candidate: ProviderMappingRevision) -> ProviderMappingRevision | None:
        with repository_engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text("SET LOCAL statement_timeout = '10s'"))
            barrier.wait(timeout=5)
            try:
                return PostgresMappingRepository(connection).append(candidate)
            except MappingConflictError:
                return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = pool.submit(append, row), pool.submit(append, competing)
        results = (first.result(timeout=15), second.result(timeout=15))
    assert sum(result is not None for result in results) == (2 if same_payload else 1)
    with repository_engine.begin() as connection:
        history = PostgresMappingRepository(connection).history(KEY)
        assert len(history) == row.revision
        assert history[-1] in results
