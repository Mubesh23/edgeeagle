"""Synthetic local fixture -> importer -> raw S3, with no upstream acquisition."""

from datetime import UTC, datetime
from pathlib import Path

from mypy_boto3_s3 import S3Client

from edgeeagle_domain.provenance import DataSourceId
from edgeeagle_domain.raw import RawCapture
from edgeeagle_ingestion.offline import LocalFileImporter
from edgeeagle_ingestion.service import OfflineDatasetImporter, ingest_raw
from edgeeagle_persistence.raw import S3RawPayloadStore
from tests.integration.test_raw_storage import raw_bucket as raw_bucket


def test_fixture_ingestion_retains_exact_bytes_and_replays(
    raw_bucket: tuple[S3Client, str],
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
