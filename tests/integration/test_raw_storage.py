"""Exercise exact retention and conditional replay against local Floci only."""

import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import boto3
import pytest
from botocore.config import Config
from botocore.exceptions import ClientError
from mypy_boto3_s3 import S3Client

from edgeeagle_domain.provenance import DataSourceId
from edgeeagle_domain.raw import RawCapture, RawPayload, RawPayloadIntegrityError, RawPayloadStore
from edgeeagle_persistence.raw import S3RawPayloadStore


@pytest.fixture
def raw_bucket() -> Iterator[tuple[S3Client, str]]:
    port = int(os.environ.get("EDGEEAGLE_FLOCI_PORT", "4566"))
    client = boto3.client(
        "s3",
        endpoint_url=f"http://127.0.0.1:{port}",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        aws_session_token="test",
        region_name="us-east-1",
        config=Config(
            s3={"addressing_style": "path"},
            proxies={},
            connect_timeout=3,
            read_timeout=5,
            retries={"max_attempts": 1},
        ),
    )
    bucket = f"edgeeagle-raw-test-{uuid4().hex}"
    client.create_bucket(Bucket=bucket)
    try:
        yield client, bucket
    finally:
        for entry in client.list_objects_v2(Bucket=bucket).get("Contents", []):
            client.delete_object(Bucket=bucket, Key=entry["Key"])
        client.delete_bucket(Bucket=bucket)
        client.close()


@pytest.mark.parametrize("body", [b"", b"\x00\xff\n", b'{ "synthetic": true }\n'])
def test_raw_storage_roundtrip_and_replay(raw_bucket: tuple[S3Client, str], body: bytes) -> None:
    client, bucket = raw_bucket
    store: RawPayloadStore = S3RawPayloadStore(client, bucket)
    capture = RawCapture(
        data_source_id=DataSourceId("synthetic/source"),
        resource="odds/sample",
        ingested_at=datetime(2026, 9, 22, tzinfo=UTC),
    )
    raw = RawPayload(capture=capture, body=body)
    assert store.get(raw.reference()) is None
    with ThreadPoolExecutor(max_workers=2) as pool:
        references = list(pool.map(store.put, [raw, raw]))
    assert references == [raw.reference(), raw.reference()]
    assert store.put(raw) == raw.reference()
    assert store.get(raw.reference()) == body
    entries = client.list_objects_v2(Bucket=bucket)["Contents"]
    assert len(entries) == 1
    key = entries[0]["Key"]
    assert "source=synthetic%2Fsource/resource=odds%2Fsample/date=2026-09-22/" in key
    # Explicitly prove the emulator enforces the precondition, not only round trips.
    with pytest.raises(ClientError) as error:
        client.put_object(Bucket=bucket, Key=key, Body=b"overwrite", IfNoneMatch="*")
    assert error.value.response["Error"]["Code"] == "PreconditionFailed"
    assert store.get(raw.reference()) == body
    later = replace(
        raw, capture=replace(capture, ingested_at=capture.ingested_at + timedelta(seconds=1))
    )
    assert store.put(later) != raw.reference()
    assert len(client.list_objects_v2(Bucket=bucket)["Contents"]) == 2
    # Simulate an out-of-band corrupt writer; the adapter must not trust S3 metadata alone.
    client.put_object(Bucket=bucket, Key=key, Body=b"corrupt")
    with pytest.raises(RawPayloadIntegrityError):
        store.get(raw.reference())
    with pytest.raises(RawPayloadIntegrityError):
        store.put(raw)
