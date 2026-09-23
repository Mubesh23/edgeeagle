"""Retained PostgreSQL receipts and Floci captures, without current-state replay reads."""

from dataclasses import replace

import pytest
from mypy_boto3_s3 import S3Client
from sqlalchemy import Engine, text

from edgeeagle_domain.mappings import MappingStatus
from edgeeagle_domain.raw import RawPayloadIntegrityError
from edgeeagle_domain.sports import EventId
from edgeeagle_ingestion.manifests import ManifestCapture, ReplayDatasetManifest, encode_manifest
from edgeeagle_ingestion.snapshot_replay import verify_manifest
from edgeeagle_ingestion.synthetic_events import normalize_mapped_fixture_events
from edgeeagle_persistence.events import PostgresEventAcceptanceRepository
from edgeeagle_persistence.fixture_references import fixture_reference_reads
from edgeeagle_persistence.mappings import PostgresMappingRepository
from edgeeagle_persistence.raw import S3RawPayloadStore
from edgeeagle_persistence.receipts import EventReceiptCodec
from tests.integration.test_mapped_normalization import seed_mapped_context
from tests.integration.test_raw_storage import raw_bucket as raw_bucket
from tests.integration.test_repositories import repository_engine as repository_engine
from tests.unit.test_event_normalization import fixture_payload
from tests.unit.test_fixture_references import NOW
from tests.unit.test_mapped_normalization import request


@pytest.mark.parametrize("failure", ["missing", "metadata", "body"])
def test_snapshot_replay_retains_context_and_rejects_lost_artifacts(
    repository_engine: Engine, raw_bucket: tuple[S3Client, str], failure: str
) -> None:
    client, bucket = raw_bucket
    store, codec = S3RawPayloadStore(client, bucket), EventReceiptCodec()
    with repository_engine.begin() as connection:
        seed_mapped_context(connection)
    base = fixture_payload()
    reads = fixture_reference_reads(repository_engine)
    candidates = []
    for resource, event_id in (("a", "e1"), ("b", "e2")):
        raw = replace(base, capture=replace(base.capture, resource=resource))
        reference = store.put(raw)
        candidates.append(
            normalize_mapped_fixture_events(
                store,
                reference,
                (replace(request(), event_id=EventId(event_id)),),
                reads,
                as_of=NOW,
            )[0]
        )
    empty = replace(base, capture=replace(base.capture, resource="z"), body=b"[]")
    empty_reference = store.put(empty)
    with repository_engine.begin() as connection:
        repository = PostgresEventAcceptanceRepository(connection)
        for candidate in candidates:
            assert repository.accept(candidate)
    with repository_engine.begin() as connection:
        evidence = candidates[0].mapping_evidence
        assert evidence is not None
        PostgresMappingRepository(connection).append(
            replace(evidence.references.revisions[3], revision=2, status=MappingStatus.REVOKED)
        )
        connection.execute(
            text("UPDATE participants SET canonical_name = 'Changed' WHERE participant_id = 'p1'")
        )
        retained = []
        for candidate in candidates:
            accepted = PostgresEventAcceptanceRepository(connection).get(candidate.event.event_id)
            assert accepted is not None
            retained.append(accepted)
    with pytest.raises(ValueError, match="revoked"):
        normalize_mapped_fixture_events(store, retained[0].raw, (request(),), reads, as_of=NOW)
    manifest = ReplayDatasetManifest(
        captures=(
            *(ManifestCapture(raw=c.raw, candidates=(c,)) for c in reversed(retained)),
            ManifestCapture(raw=empty_reference, candidates=()),
        )
    )
    body = encode_manifest(manifest, codec)
    # No DB transaction/reader is provided; output comes from verified retained bytes/context.
    assert verify_manifest(body, codec, store) == ((retained[0],), (retained[1],), ())
    assert encode_manifest(manifest, codec) == body
    for candidate in retained:
        assert candidate.mapping_evidence is not None
        assert candidate.mapping_evidence.references.home.canonical_name == "Internal home"
        assert candidate.raw.capture.available_at is None
        assert store.get(candidate.raw) == base.body
    objects = client.list_objects_v2(Bucket=bucket)["Contents"]
    assert len(objects) == 3
    # Simulate loss/corruption only in this test's disposable final-capture object.
    key = next(entry["Key"] for entry in objects if "/resource=z/" in entry["Key"])
    if failure == "missing":
        client.delete_object(Bucket=bucket, Key=key)
    else:
        metadata = client.head_object(Bucket=bucket, Key=key)["Metadata"]
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=b"{}" if failure == "body" else empty.body,
            Metadata={} if failure == "metadata" else metadata,
        )
    with pytest.raises((FileNotFoundError, RawPayloadIntegrityError)):
        verify_manifest(body, codec, store)
    with repository_engine.begin() as connection:
        repository = PostgresEventAcceptanceRepository(connection)
        assert [repository.get(c.event.event_id) for c in retained] == retained
        assert connection.scalar(text("SELECT count(*) FROM events")) == 2
        assert connection.scalar(text("SELECT count(*) FROM event_normalizations")) == 2
        assert connection.scalar(text("SELECT count(*) FROM event_outbox")) == 0
    assert len(client.list_objects_v2(Bucket=bucket)["Contents"]) == (
        2 if failure == "missing" else 3
    )
