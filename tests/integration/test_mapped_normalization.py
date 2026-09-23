from dataclasses import replace
from datetime import timedelta

import pytest
from mypy_boto3_s3 import S3Client
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import InternalError

from edgeeagle_domain.mappings import MappingStatus
from edgeeagle_ingestion.events import EventAcceptanceConflict
from edgeeagle_ingestion.identity import acceptance_key
from edgeeagle_ingestion.synthetic_events import (
    normalize_mapped_fixture_events,
    replay_mapped_fixture_events,
)
from edgeeagle_persistence.events import PostgresEventAcceptanceRepository
from edgeeagle_persistence.fixture_references import (
    PostgresFixtureReferenceResolver,
    fixture_reference_reads,
)
from edgeeagle_persistence.mappings import PostgresMappingRepository
from edgeeagle_persistence.raw import S3RawPayloadStore
from tests.integration.test_event_acceptance import seed
from tests.integration.test_raw_storage import raw_bucket as raw_bucket
from tests.integration.test_repositories import repository_engine as repository_engine
from tests.unit.test_event_normalization import fixture_payload
from tests.unit.test_fixture_references import NOW, setup_references
from tests.unit.test_mapped_normalization import request


def seed_mapped_context(connection: Connection) -> None:
    seed(connection)
    keys, mappings, _ = setup_references()
    repository = PostgresMappingRepository(connection)
    for key in keys.ordered():
        repository.append(mappings.history(key)[0])


def test_mapped_snapshot_pins_mapping_and_canonical_context(repository_engine: Engine) -> None:
    with repository_engine.begin() as connection:
        seed_mapped_context(connection)
    reads = fixture_reference_reads(repository_engine)
    with reads() as resolver:
        original = resolver.resolve(request().references, as_of=NOW)
        with repository_engine.begin() as writer:
            revision = replace(original.revisions[3], revision=2, mapping_method="reviewed-fixture")
            PostgresMappingRepository(writer).append(revision)
            writer.execute(
                text(
                    "UPDATE participants SET canonical_name = 'Changed' WHERE participant_id = 'p1'"
                )
            )
        assert resolver.resolve(request().references, as_of=NOW) == original
    with pytest.raises(RuntimeError, match="active"):
        resolver.resolve(request().references, as_of=NOW)
    with reads() as fresh:
        current = fresh.resolve(request().references, as_of=NOW)
        assert current.revisions[3] == revision
        assert current.home.canonical_name == "Changed"
    assert original.home.canonical_name == "Internal home"


def test_mapped_resolver_guards_and_read_only_enforcement(repository_engine: Engine) -> None:
    with repository_engine.begin() as connection:
        seed_mapped_context(connection)
        with pytest.raises(RuntimeError, match="REPEATABLE READ"):
            PostgresFixtureReferenceResolver(connection).resolve(request().references, as_of=NOW)
    with repository_engine.connect().execution_options(
        isolation_level="REPEATABLE READ"
    ) as connection:
        with connection.begin():
            with pytest.raises(RuntimeError, match="read-only"):
                PostgresFixtureReferenceResolver(connection).resolve(
                    request().references, as_of=NOW
                )
            connection.execute(text("SET TRANSACTION READ ONLY"))
            resolver = PostgresFixtureReferenceResolver(connection)
            assert resolver.resolve(request().references, as_of=NOW)
            with pytest.raises(InternalError), connection.begin_nested():
                connection.execute(text("UPDATE sports SET name = 'Not allowed'"))


def test_mapped_normalization_retains_receipt_after_revision_and_revocation(
    repository_engine: Engine,
    raw_bucket: tuple[S3Client, str],
) -> None:
    with repository_engine.begin() as connection:
        seed_mapped_context(connection)
    raw = fixture_payload()
    client, bucket = raw_bucket
    store = S3RawPayloadStore(client, bucket)
    assert store.put(raw) == raw.reference()
    reads = fixture_reference_reads(repository_engine)
    original = normalize_mapped_fixture_events(
        store, raw.reference(), (request(),), reads, as_of=NOW
    )[0]
    assert original.mapping_evidence is not None
    with repository_engine.begin() as connection:
        assert PostgresEventAcceptanceRepository(connection).accept(original)
        revision = replace(
            original.mapping_evidence.references.revisions[3],
            revision=2,
            available_at=NOW + timedelta(days=1),
            ingested_at=NOW + timedelta(days=1),
        )
        PostgresMappingRepository(connection).append(revision)
    assert (
        normalize_mapped_fixture_events(store, raw.reference(), (request(),), reads, as_of=NOW)[0]
        == original
    )
    changed = normalize_mapped_fixture_events(
        store, raw.reference(), (request(),), reads, as_of=revision.available_at
    )[0]
    assert changed.event == original.event
    with repository_engine.begin() as connection:
        repository = PostgresEventAcceptanceRepository(connection)
        with pytest.raises(EventAcceptanceConflict):
            repository.accept(changed)
        assert repository.get(original.event.event_id) == original
        assert not repository.accept(original)
        PostgresMappingRepository(connection).append(
            replace(revision, revision=3, status=MappingStatus.REVOKED)
        )
        connection.execute(
            text("UPDATE participants SET canonical_name = 'Changed' WHERE participant_id = 'p1'")
        )
    with pytest.raises(ValueError, match="revoked"):
        normalize_mapped_fixture_events(
            store, raw.reference(), (request(),), reads, as_of=revision.available_at
        )
    with repository_engine.begin() as connection:
        retained = PostgresEventAcceptanceRepository(connection).get(original.event.event_id)
        assert retained == original
        assert connection.scalar(text("SELECT count(*) FROM events")) == 1
    assert retained is not None
    # No open database transaction or current reference reader is passed to replay.
    replayed = replay_mapped_fixture_events(store, retained.raw, (retained,))[0]
    assert replayed == retained
    assert acceptance_key(replayed) == acceptance_key(original)
    assert replayed.mapping_evidence is not None
    assert replayed.mapping_evidence.references.home.canonical_name == "Internal home"
    assert replayed.raw.capture.available_at is None
    with repository_engine.begin() as connection:
        repository = PostgresEventAcceptanceRepository(connection)
        assert not repository.accept(replayed)  # Existing receipt retry, not fresh approval.
        assert repository.get(original.event.event_id) == retained
        assert connection.scalar(text("SELECT count(*) FROM event_normalizations")) == 1
        assert connection.scalar(text("SELECT count(*) FROM event_outbox")) == 0
    assert store.get(raw.reference()) == raw.body
    assert len(client.list_objects_v2(Bucket=bucket)["Contents"]) == 1
