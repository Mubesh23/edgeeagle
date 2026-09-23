"""Synthetic local fixture -> importer -> raw S3, with no upstream acquisition."""

from datetime import UTC, datetime
from pathlib import Path

from mypy_boto3_s3 import S3Client
from sqlalchemy import Engine

from edgeeagle_domain.provenance import DataSourceId
from edgeeagle_domain.raw import RawCapture
from edgeeagle_ingestion.offline import LocalFileImporter
from edgeeagle_ingestion.service import OfflineDatasetImporter, ingest_raw
from edgeeagle_ingestion.synthetic_events import normalize_fixture_events
from edgeeagle_persistence.events import PostgresEventAcceptanceRepository
from edgeeagle_persistence.raw import S3RawPayloadStore
from tests.integration.test_event_acceptance import seed
from tests.integration.test_raw_storage import raw_bucket as raw_bucket
from tests.integration.test_repositories import repository_engine as repository_engine
from tests.unit.test_event_normalization import binding


def test_fixture_ingestion_retains_exact_bytes_and_replays(
    raw_bucket: tuple[S3Client, str],
    repository_engine: Engine,
) -> None:
    client, bucket = raw_bucket
    path = Path(__file__).parents[1] / "fixtures/providers/the_odds_api/odds-success.json"
    capture = RawCapture(
        data_source_id=DataSourceId("synthetic-fixtures"),
        resource="the-odds-api-soccer-h2h-v1",
        ingested_at=datetime(2026, 9, 22, tzinfo=UTC),
    )
    importer: OfflineDatasetImporter = LocalFileImporter(path, capture, max_bytes=4096)
    store = S3RawPayloadStore(client, bucket)
    receipt = ingest_raw(importer, store)
    assert store.get(receipt) == path.read_bytes()
    assert receipt.capture == capture
    assert receipt.capture.observed_at is None
    assert receipt.capture.available_at is None
    assert ingest_raw(importer, store) == receipt
    assert len(client.list_objects_v2(Bucket=bucket)["Contents"]) == 1
    candidates = normalize_fixture_events(store, receipt, (binding(),))
    assert candidates[0].raw == receipt
    assert candidates[0].event.event_id == binding().event_id
    assert candidates[0].raw.capture.available_at is None
    assert store.get(receipt) == path.read_bytes()
    assert normalize_fixture_events(store, receipt, (binding(),)) == candidates
    assert len(client.list_objects_v2(Bucket=bucket)["Contents"]) == 1
    with repository_engine.begin() as connection:
        seed(connection)
        repository = PostgresEventAcceptanceRepository(connection)
        assert repository.accept(candidates[0]) is True
    with repository_engine.begin() as connection:
        repository = PostgresEventAcceptanceRepository(connection)
        assert repository.accept(candidates[0]) is False
        accepted = repository.get(candidates[0].event.event_id)
        assert accepted is not None
        assert accepted.raw == receipt
        assert store.get(accepted.raw) == path.read_bytes()
