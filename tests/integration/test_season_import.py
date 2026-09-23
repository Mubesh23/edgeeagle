"""Whole authored seasons across local PostgreSQL/Floci; never real provider files."""

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest
from mypy_boto3_s3 import S3Client
from sqlalchemy import Engine, text

from edgeeagle_domain.mappings import MappingStatus
from edgeeagle_domain.raw import RawPayload
from edgeeagle_ingestion.events import EventAcceptanceConflict
from edgeeagle_ingestion.football_data import (
    MAX_CSV_BYTES,
    FootballDataRequest,
    normalize_season_results,
)
from edgeeagle_ingestion.football_data_season_import import import_season_dataset
from edgeeagle_ingestion.offline import LocalFileImporter
from edgeeagle_ingestion.season_bundle import decode_root, verify_bundle
from edgeeagle_persistence.events import PostgresEventAcceptanceRepository
from edgeeagle_persistence.fixture_references import fixture_reference_reads
from edgeeagle_persistence.mappings import PostgresMappingRepository
from edgeeagle_persistence.raw import S3RawPayloadStore
from edgeeagle_persistence.season_storage import S3SeasonObjectStore
from tests.integration.test_football_data_import import acceptance_transactions
from tests.integration.test_mapped_normalization import seed_mapped_context
from tests.integration.test_raw_storage import raw_bucket as raw_bucket
from tests.integration.test_repositories import repository_engine as repository_engine
from tests.unit.test_dataset_manifest import CODEC
from tests.unit.test_fixture_references import NOW
from tests.unit.test_football_data_season import season_batch


def setup_import(
    engine: Engine, bucket: tuple[S3Client, str], path: Path, *, count: int = 380
) -> tuple[
    RawPayload,
    tuple[FootballDataRequest, ...],
    S3RawPayloadStore,
    S3SeasonObjectStore,
    Callable[[], str],
]:
    raw, requests = season_batch(count)
    path.write_bytes(raw.body)
    with engine.begin() as connection:
        seed_mapped_context(connection)
        # This authored fixture spans 380 daily matches, not an actual league schedule.
        connection.execute(text("UPDATE seasons SET ends_at = '2028-01-01T00:00:00Z'"))
    client, name = bucket
    store, objects = S3RawPayloadStore(client, name), S3SeasonObjectStore(client, name, CODEC)
    importer = LocalFileImporter(path, raw.capture, max_bytes=MAX_CSV_BYTES)

    def run() -> str:
        return import_season_dataset(
            importer,
            store,
            requests,
            fixture_reference_reads(engine),
            acceptance_transactions(engine),
            objects,
            CODEC,
            as_of=NOW,
        )

    return raw, requests, store, objects, run


def test_season_import_complete_retry_replay_after_reference_edits(
    repository_engine: Engine, raw_bucket: tuple[S3Client, str], tmp_path: Path
) -> None:
    raw, requests, store, objects, run = setup_import(
        repository_engine, raw_bucket, tmp_path / "authored.csv"
    )
    # Competing initial imports must converge, not just sequential retries.
    with ThreadPoolExecutor(max_workers=2) as pool:
        hashes = list(pool.map(lambda _: run(), range(2)))
    assert hashes[0] == hashes[1] == run()
    body = objects.get(hashes[0])
    assert body is not None
    index = decode_root(body)
    assert index.row_count == 380 and len(index.page_hashes) == 6
    assert store.get(raw.reference()) == raw.body
    with repository_engine.begin() as connection:
        repo = PostgresEventAcceptanceRepository(connection)
        retained = tuple(repo.get(r.event_id) for r in requests)
        assert all(c is not None for c in retained)
        assert connection.scalar(text("SELECT count(*) FROM events")) == 380
        assert connection.scalar(text("SELECT count(*) FROM event_normalizations")) == 380
        assert connection.scalar(text("SELECT count(*) FROM event_outbox")) == 0
        candidate = retained[0]
        assert candidate is not None and candidate.mapping_evidence is not None
        revision = candidate.mapping_evidence.references.revisions[3]
        PostgresMappingRepository(connection).append(
            replace(revision, revision=2, status=MappingStatus.REVOKED)
        )
        connection.execute(text("UPDATE participants SET canonical_name = 'Changed'"))
    with pytest.raises(ValueError, match="revoked"):
        run()
    assert verify_bundle(body, CODEC, objects, store) == retained
    assert all(c is not None and c.raw.capture.available_at is None for c in retained)
    client, bucket = raw_bucket
    assert len(client.list_objects_v2(Bucket=bucket)["Contents"]) == 8  # raw, six pages, root
    # A surviving root does not make an incomplete bundle successful.
    client.delete_object(
        Bucket=bucket,
        Key=f"snapshots/football-data-seasons/v1/{index.page_hashes[-1]}.json",
    )
    assert objects.get(hashes[0]) == body
    with pytest.raises(FileNotFoundError):
        verify_bundle(body, CODEC, objects, store)


def test_season_import_last_conflict_rolls_back_all_prior_rows(
    repository_engine: Engine, raw_bucket: tuple[S3Client, str], tmp_path: Path
) -> None:
    raw, requests, store, _, run = setup_import(
        repository_engine, raw_bucket, tmp_path / "authored.csv"
    )
    store.put(raw)
    values = normalize_season_results(
        store, raw.reference(), requests, fixture_reference_reads(repository_engine), as_of=NOW
    )
    conflict = replace(values[-1], context_version="different")
    with repository_engine.begin() as connection:
        PostgresEventAcceptanceRepository(connection).accept(conflict)
    with pytest.raises(EventAcceptanceConflict):
        run()
    with repository_engine.begin() as connection:
        repo = PostgresEventAcceptanceRepository(connection)
        assert all(repo.get(r.event_id) is None for r in requests[:-1])
        assert repo.get(requests[-1].event_id) == conflict
        assert connection.scalar(text("SELECT count(*) FROM events")) == 1
        assert connection.scalar(text("SELECT count(*) FROM event_normalizations")) == 1
        assert connection.scalar(text("SELECT count(*) FROM event_outbox")) == 0
    client, bucket = raw_bucket
    assert len(client.list_objects_v2(Bucket=bucket)["Contents"]) == 1


@pytest.mark.parametrize("fail_at", [2, 3])
def test_season_import_recovers_partial_pages_or_root_failure(
    repository_engine: Engine,
    raw_bucket: tuple[S3Client, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fail_at: int,
) -> None:
    _, requests, store, objects, run = setup_import(
        repository_engine, raw_bucket, tmp_path / "authored.csv", count=65
    )
    original_put, attempts = objects.put, []

    def failing_put(body: bytes) -> str:
        attempts.append(body)
        if len(attempts) == fail_at:
            raise OSError("storage unavailable")
        return original_put(body)

    with monkeypatch.context() as patch:
        patch.setattr(objects, "put", failing_put)
        with pytest.raises(OSError):
            run()
    with repository_engine.begin() as connection:
        retained = tuple(
            PostgresEventAcceptanceRepository(connection).get(r.event_id) for r in requests
        )
        assert connection.scalar(text("SELECT count(*) FROM event_normalizations")) == 65
        assert connection.scalar(text("SELECT count(*) FROM event_outbox")) == 0
    client, bucket = raw_bucket
    assert len(client.list_objects_v2(Bucket=bucket)["Contents"]) == fail_at  # raw + pages
    digest = run()
    body = objects.get(digest)
    assert body is not None
    assert verify_bundle(body, CODEC, objects, store) == retained
    assert run() == digest
    assert len(client.list_objects_v2(Bucket=bucket)["Contents"]) == 4


def test_season_import_malformed_last_row_has_no_canonical_effects(
    repository_engine: Engine, raw_bucket: tuple[S3Client, str], tmp_path: Path
) -> None:
    raw, requests = season_batch(380)
    raw = replace(raw, body=raw.body.rsplit(b",2,1,H", 1)[0] + b",bad,1,H\n")
    path = tmp_path / "bad.csv"
    path.write_bytes(raw.body)
    client, bucket = raw_bucket
    store = S3RawPayloadStore(client, bucket)
    reads, transactions, objects = Mock(), Mock(), Mock()
    with pytest.raises(ValueError, match="goals"):
        import_season_dataset(
            LocalFileImporter(path, raw.capture, max_bytes=MAX_CSV_BYTES),
            store,
            requests,
            reads,
            transactions,
            objects,
            CODEC,
            as_of=NOW,
        )
    reads.assert_not_called()
    transactions.assert_not_called()
    objects.put.assert_not_called()
    assert store.get(raw.reference()) == raw.body
    with repository_engine.begin() as connection:
        assert connection.scalar(text("SELECT count(*) FROM events")) == 0
