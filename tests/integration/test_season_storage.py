"""Season roots/pages use immutable conditional objects in disposable Floci buckets."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from botocore.exceptions import ClientError
from mypy_boto3_s3 import S3Client

from edgeeagle_ingestion.season_bundle import (
    SeasonObjectIntegrityError,
    build_bundle,
    content_hash,
)
from edgeeagle_persistence.season_storage import S3SeasonObjectStore
from tests.integration.test_raw_storage import raw_bucket as raw_bucket
from tests.unit.test_dataset_manifest import CODEC
from tests.unit.test_season_bundle import values


@pytest.mark.parametrize("kind", ["root", "page"])
def test_season_storage_condition_concurrent_retry_and_corruption(
    raw_bucket: tuple[S3Client, str], kind: str
) -> None:
    client, bucket = raw_bucket
    raw, candidates = values(2)
    root, pages = build_bundle(raw.reference(), candidates, CODEC)
    body = root if kind == "root" else pages[0]
    digest = content_hash(body)
    store = S3SeasonObjectStore(client, bucket, CODEC)
    assert store.get(digest) is None
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(store.put, [body, body])) == [digest, digest]
    assert store.put(body) == digest
    assert store.get(digest) == body
    key = f"snapshots/football-data-seasons/v1/{digest}.json"
    assert len(client.list_objects_v2(Bucket=bucket)["Contents"]) == 1
    assert client.head_object(Bucket=bucket, Key=key)["ContentType"] == "application/json"
    with pytest.raises(ClientError) as error:
        client.put_object(Bucket=bucket, Key=key, Body=b"overwrite", IfNoneMatch="*")
    assert error.value.response["Error"]["Code"] == "PreconditionFailed"
    assert store.get(digest) == body
    # Metadata is incidental, not an identity claim.
    client.put_object(Bucket=bucket, Key=key, Body=body, Metadata={"note": "test"})
    assert store.put(body) == digest
    for corrupt in (b"corrupt", pages[0] if kind == "root" else root):
        client.put_object(Bucket=bucket, Key=key, Body=corrupt)
        with pytest.raises(SeasonObjectIntegrityError):
            store.get(digest)
        with pytest.raises(SeasonObjectIntegrityError):
            store.put(body)
        with client.get_object(Bucket=bucket, Key=key)["Body"] as stream:
            assert stream.read() == corrupt
