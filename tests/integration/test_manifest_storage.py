"""Immutable manifest objects in disposable local Floci buckets only."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from botocore.exceptions import ClientError
from mypy_boto3_s3 import S3Client

from edgeeagle_ingestion.manifest_storage import ManifestIntegrityError, ReplayManifestStore
from edgeeagle_ingestion.manifests import ManifestCapture, ReplayDatasetManifest, encode_manifest
from edgeeagle_persistence.manifest_storage import S3ReplayManifestStore
from tests.integration.test_raw_storage import raw_bucket as raw_bucket
from tests.unit.test_dataset_manifest import CODEC, manifest


def test_manifest_storage_roundtrip_concurrent_retry_and_condition(
    raw_bucket: tuple[S3Client, str],
) -> None:
    client, bucket = raw_bucket
    store: ReplayManifestStore = S3ReplayManifestStore(client, bucket, CODEC)
    body = encode_manifest(manifest(), CODEC)
    version = json.loads(body)["dataset_version"]
    assert store.get(version) is None
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(store.put, [body, body])) == [version, version]
    assert store.put(body) == version
    assert store.get(version) == body
    objects = client.list_objects_v2(Bucket=bucket)["Contents"]
    assert len(objects) == 1
    key = f"snapshots/replay-manifests/v1/{version}.json"
    assert objects[0]["Key"] == key
    assert client.head_object(Bucket=bucket, Key=key)["ContentType"] == "application/json"
    with pytest.raises(ClientError) as error:
        client.put_object(Bucket=bucket, Key=key, Body=b"overwrite", IfNoneMatch="*")
    assert error.value.response["Error"]["Code"] == "PreconditionFailed"
    assert store.get(version) == body
    # Incidental metadata is not the content identity.
    client.put_object(Bucket=bucket, Key=key, Body=body, Metadata={"note": "test-only"})
    assert store.get(version) == body
    assert store.put(body) == version


@pytest.mark.parametrize("corruption", ["malformed", "wrong-version"])
def test_manifest_storage_corruption_is_not_overwritten(
    raw_bucket: tuple[S3Client, str],
    corruption: str,
) -> None:
    client, bucket = raw_bucket
    store = S3ReplayManifestStore(client, bucket, CODEC)
    model = manifest()
    body = encode_manifest(model, CODEC)
    version = store.put(body)
    key = f"snapshots/replay-manifests/v1/{version}.json"
    corrupt = b"corrupt"
    if corruption == "wrong-version":
        # Structurally valid, deliberately incomplete: storage does not read raw.
        other = ReplayDatasetManifest(
            captures=(ManifestCapture(raw=model.captures[0].raw, candidates=()),)
        )
        corrupt = encode_manifest(other, CODEC)
        other_version = store.put(corrupt)
        assert other_version != version
        assert store.get(other_version) == corrupt
    client.put_object(Bucket=bucket, Key=key, Body=corrupt)
    with pytest.raises(ManifestIntegrityError):
        store.get(version)
    with pytest.raises(ManifestIntegrityError):
        store.put(body)
    response = client.get_object(Bucket=bucket, Key=key)
    with response["Body"] as stream:
        assert stream.read(len(corrupt) + 1) == corrupt
