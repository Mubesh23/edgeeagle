"""Authored Sportmonks bytes through local immutable raw retention and reading."""

import pytest
from mypy_boto3_s3 import S3Client

from edgeeagle_domain.raw import RawPayloadIntegrityError
from edgeeagle_ingestion.offline import LocalFileImporter
from edgeeagle_ingestion.service import ingest_raw
from edgeeagle_ingestion.sportmonks_manifest import read_sportmonks_capture
from edgeeagle_persistence.raw import S3RawPayloadStore
from tests.integration.test_raw_storage import raw_bucket as raw_bucket
from tests.unit.test_sportmonks_manifest import FIXTURE, manifest


def test_retained_fixture_is_repeatable_and_tampering_fails_closed(
    raw_bucket: tuple[S3Client, str],
) -> None:
    client, bucket = raw_bucket
    store = S3RawPayloadStore(client, bucket)
    m = manifest()
    with pytest.raises(FileNotFoundError):
        read_sportmonks_capture(store, m)
    importer = LocalFileImporter(FIXTURE, m.raw.capture, max_bytes=1024 * 1024)
    assert ingest_raw(importer, store) == m.raw
    first = read_sportmonks_capture(store, m)
    assert first.fixture_id == 910001
    assert first.home.participant_id == 940001
    assert ingest_raw(importer, store) == m.raw
    assert read_sportmonks_capture(store, m) == first
    assert store.get(m.raw) == FIXTURE.read_bytes()
    assert m.usage == "SYNTHETIC_ONLY" and m.raw.capture.available_at is None
    entries = client.list_objects_v2(Bucket=bucket)["Contents"]
    assert len(entries) == 1
    # Out-of-band corruption only inside this disposable test bucket.
    client.put_object(Bucket=bucket, Key=entries[0]["Key"], Body=b"corrupt")
    with pytest.raises(RawPayloadIntegrityError):
        read_sportmonks_capture(store, m)
