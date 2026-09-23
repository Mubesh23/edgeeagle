"""Local file -> raw -> transactional receipts -> stored snapshot -> CSV replay."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest
from mypy_boto3_s3 import S3Client
from sqlalchemy import Engine, text

from edgeeagle_domain.mappings import MappingStatus
from edgeeagle_domain.raw import RawPayloadIntegrityError
from edgeeagle_ingestion.events import EventAcceptanceConflict, EventAcceptanceRepository
from edgeeagle_ingestion.football_data import MAX_CSV_BYTES, normalize_results
from edgeeagle_ingestion.football_data_import import AcceptanceTransactions, import_results_dataset
from edgeeagle_ingestion.manifests import decode_manifest
from edgeeagle_ingestion.offline import LocalFileImporter
from edgeeagle_ingestion.snapshot_replay import verify_manifest
from edgeeagle_persistence.events import PostgresEventAcceptanceRepository
from edgeeagle_persistence.fixture_references import fixture_reference_reads
from edgeeagle_persistence.manifest_storage import S3ReplayManifestStore
from edgeeagle_persistence.mappings import PostgresMappingRepository
from edgeeagle_persistence.raw import S3RawPayloadStore
from edgeeagle_persistence.receipts import EventReceiptCodec
from tests.integration.test_mapped_normalization import seed_mapped_context
from tests.integration.test_raw_storage import raw_bucket as raw_bucket
from tests.integration.test_repositories import repository_engine as repository_engine
from tests.unit.test_fixture_references import NOW
from tests.unit.test_football_data import CSV_PATH, csv_payload, csv_requests


def acceptance_transactions(engine: Engine) -> AcceptanceTransactions:
    @contextmanager
    def transactions() -> Iterator[EventAcceptanceRepository]:
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text("SET LOCAL statement_timeout = '10s'"))
            yield PostgresEventAcceptanceRepository(connection)

    return transactions


@pytest.mark.parametrize("loss", ["missing", "body", "metadata"])
def test_football_data_import_reproduces_retained_results_after_reference_edits(
    repository_engine: Engine,
    raw_bucket: tuple[S3Client, str],
    loss: str,
) -> None:
    client, bucket = raw_bucket
    raw, codec = csv_payload(), EventReceiptCodec()
    store, manifests = (
        S3RawPayloadStore(client, bucket),
        S3ReplayManifestStore(client, bucket, codec),
    )
    with repository_engine.begin() as connection:
        seed_mapped_context(connection)
    importer = LocalFileImporter(CSV_PATH, raw.capture, max_bytes=MAX_CSV_BYTES)
    reads, transactions = (
        fixture_reference_reads(repository_engine),
        acceptance_transactions(repository_engine),
    )

    def run() -> str:
        return import_results_dataset(
            importer, store, csv_requests(), reads, transactions, manifests, codec, as_of=NOW
        )

    version = run()
    assert run() == version
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda _: run(), range(2))) == [version, version]
    assert store.get(raw.reference()) == CSV_PATH.read_bytes()
    body = manifests.get(version)
    assert body is not None
    model = decode_manifest(body, codec)
    assert model.kind == "FOOTBALL_DATA_RESULTS_REPLAY"
    assert model.usage == "REPLAY_ONLY"
    with repository_engine.begin() as connection:
        repository = PostgresEventAcceptanceRepository(connection)
        retained = tuple(repository.get(r.event_id) for r in csv_requests())
        assert all(c is not None for c in retained)
        assert connection.scalar(text("SELECT count(*) FROM events")) == 2
        assert (
            connection.scalar(
                text(
                    "SELECT count(*) FROM event_normalizations "
                    "WHERE snapshot->'format' = '3'::jsonb"
                )
            )
            == 2
        )
        candidate = retained[0]
        assert candidate is not None and candidate.mapping_evidence is not None
        revision = candidate.mapping_evidence.references.revisions[3]
        PostgresMappingRepository(connection).append(
            replace(revision, revision=2, status=MappingStatus.REVOKED)
        )
        connection.execute(
            text(
                "UPDATE participants SET canonical_name = 'Edited after import' "
                "WHERE participant_id = 'p1'"
            )
        )
    with pytest.raises(ValueError, match="revoked"):
        normalize_results(store, raw.reference(), csv_requests(), reads, as_of=NOW)
    assert verify_manifest(body, codec, store) == (retained,)
    for candidate in retained:
        assert candidate is not None and candidate.soccer_result is not None
        assert candidate.raw.capture.available_at is None
        assert candidate.mapping_evidence is not None
        assert candidate.mapping_evidence.references.home.canonical_name == "Internal home"
    objects = client.list_objects_v2(Bucket=bucket)["Contents"]
    assert len(objects) == 2
    key = next(entry["Key"] for entry in objects if entry["Key"].startswith("raw/"))
    if loss == "missing":
        client.delete_object(Bucket=bucket, Key=key)
    else:
        metadata = client.head_object(Bucket=bucket, Key=key)["Metadata"]
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=b"corrupt" if loss == "body" else raw.body,
            Metadata={} if loss == "metadata" else metadata,
        )
    retrieved = manifests.get(version)
    assert retrieved == body
    with pytest.raises((FileNotFoundError, RawPayloadIntegrityError)):
        verify_manifest(retrieved, codec, store)
    with repository_engine.begin() as connection:
        assert (
            tuple(
                PostgresEventAcceptanceRepository(connection).get(r.event_id)
                for r in csv_requests()
            )
            == retained
        )
        assert connection.scalar(text("SELECT count(*) FROM event_outbox")) == 0
    client.delete_object(Bucket=bucket, Key=f"snapshots/replay-manifests/v1/{version}.json")
    assert manifests.get(version) is None


def test_football_data_import_batch_conflict_rolls_back_prior_rows(
    repository_engine: Engine,
    raw_bucket: tuple[S3Client, str],
) -> None:
    client, bucket = raw_bucket
    raw, codec = csv_payload(), EventReceiptCodec()
    store, manifests = (
        S3RawPayloadStore(client, bucket),
        S3ReplayManifestStore(client, bucket, codec),
    )
    with repository_engine.begin() as connection:
        seed_mapped_context(connection)
    store.put(raw)
    reads = fixture_reference_reads(repository_engine)
    values = normalize_results(store, raw.reference(), csv_requests(), reads, as_of=NOW)
    conflicting = replace(values[1], context_version="other-context")
    with repository_engine.begin() as connection:
        PostgresEventAcceptanceRepository(connection).accept(conflicting)
    with pytest.raises(EventAcceptanceConflict):
        import_results_dataset(
            LocalFileImporter(CSV_PATH, raw.capture, max_bytes=MAX_CSV_BYTES),
            store,
            csv_requests(),
            reads,
            acceptance_transactions(repository_engine),
            manifests,
            codec,
            as_of=NOW,
        )
    with repository_engine.begin() as connection:
        repository = PostgresEventAcceptanceRepository(connection)
        assert repository.get(values[0].event.event_id) is None
        assert repository.get(values[1].event.event_id) == conflicting
        assert connection.scalar(text("SELECT count(*) FROM event_normalizations")) == 1
    assert len(client.list_objects_v2(Bucket=bucket)["Contents"]) == 1
    assert store.get(raw.reference()) == raw.body


def test_football_data_import_keeps_bad_raw_without_partial_canonical_effects(
    repository_engine: Engine,
    raw_bucket: tuple[S3Client, str],
    tmp_path: Path,
) -> None:
    client, bucket = raw_bucket
    raw = replace(csv_payload(), body=csv_payload().body.replace(b",0,0,D,", b",bad,0,D,"))
    path = tmp_path / "invalid.csv"
    path.write_bytes(raw.body)
    codec, store = EventReceiptCodec(), S3RawPayloadStore(client, bucket)
    manifests = S3ReplayManifestStore(client, bucket, codec)
    # No references seeded: malformed final row must fail before any mapping query/write.
    reads = Mock()
    with pytest.raises(ValueError, match="goals"):
        import_results_dataset(
            LocalFileImporter(path, raw.capture, max_bytes=MAX_CSV_BYTES),
            store,
            csv_requests(),
            reads,
            acceptance_transactions(repository_engine),
            manifests,
            codec,
            as_of=NOW,
        )
    reads.assert_not_called()
    assert store.get(raw.reference()) == raw.body
    with repository_engine.begin() as connection:
        assert connection.scalar(text("SELECT count(*) FROM events")) == 0
        assert connection.scalar(text("SELECT count(*) FROM event_normalizations")) == 0
    assert len(client.list_objects_v2(Bucket=bucket)["Contents"]) == 1


def test_football_data_import_recovers_manifest_failure_with_exact_retry(
    repository_engine: Engine,
    raw_bucket: tuple[S3Client, str],
) -> None:
    client, bucket = raw_bucket
    raw, codec = csv_payload(), EventReceiptCodec()
    store, manifests = (
        S3RawPayloadStore(client, bucket),
        S3ReplayManifestStore(client, bucket, codec),
    )
    with repository_engine.begin() as connection:
        seed_mapped_context(connection)
    failed = Mock()
    failed.put.side_effect = OSError("storage unavailable after commit")
    importer = LocalFileImporter(CSV_PATH, raw.capture, max_bytes=MAX_CSV_BYTES)
    reads, transactions = (
        fixture_reference_reads(repository_engine),
        acceptance_transactions(repository_engine),
    )
    with pytest.raises(OSError):
        import_results_dataset(
            importer, store, csv_requests(), reads, transactions, failed, codec, as_of=NOW
        )
    with repository_engine.begin() as connection:
        assert connection.scalar(text("SELECT count(*) FROM event_normalizations")) == 2
    assert len(client.list_objects_v2(Bucket=bucket)["Contents"]) == 1
    version = import_results_dataset(
        importer, store, csv_requests(), reads, transactions, manifests, codec, as_of=NOW
    )
    body = manifests.get(version)
    assert body == failed.put.call_args.args[0]
    assert body is not None
    assert len(verify_manifest(body, codec, store)[0]) == 2
    assert len(client.list_objects_v2(Bucket=bucket)["Contents"]) == 2
