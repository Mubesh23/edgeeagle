"""Network-disabled manifest storage contract checks (ADR-027)."""

import json
from dataclasses import replace
from io import BytesIO
from typing import Any
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError

from edgeeagle_ingestion.manifest_storage import ManifestIntegrityError, ReplayManifestStore
from edgeeagle_ingestion.manifests import (
    MAX_MANIFEST_BYTES,
    ManifestCapture,
    ReplayDatasetManifest,
    encode_manifest,
)
from edgeeagle_persistence.manifest_storage import S3ReplayManifestStore
from tests.unit.test_dataset_manifest import CODEC, manifest
from tests.unit.test_fixture_replay import retained


def encoded() -> tuple[bytes, str]:
    body = encode_manifest(manifest(), CODEC)
    return body, json.loads(body)["dataset_version"]


def service_error(code: str) -> ClientError:
    return ClientError({"Error": {"Code": code}}, "StorageOperation")


def test_exact_conditional_write_read_and_retry() -> None:
    client = Mock()
    store: ReplayManifestStore = S3ReplayManifestStore(client, "test-bucket", CODEC)
    body, version = encoded()
    assert store.put(body) == version
    client.put_object.assert_called_once_with(
        Bucket="test-bucket",
        Key=f"snapshots/replay-manifests/v1/{version}.json",
        Body=body,
        ContentType="application/json",
        IfNoneMatch="*",
    )
    client.get_object.assert_not_called()
    for retry in (False, True):
        stream = BytesIO(body)
        client.get_object.return_value = {
            "Body": stream,
            "ContentLength": len(body),
            "Metadata": {"incidental": "ignored"},
        }
        if retry:
            client.put_object.side_effect = service_error("PreconditionFailed")
            assert store.put(body) == version
        else:
            assert store.get(version) == body
        assert stream.closed
        client.get_object.assert_called_with(
            Bucket="test-bucket", Key=f"snapshots/replay-manifests/v1/{version}.json"
        )


@pytest.mark.parametrize(
    "version", [None, 1, b"a" * 64, "", "A" * 64, "g" * 64, "a" * 63, "../x", "a" * 64 + "\n"]
)
def test_invalid_version_before_io(version: Any) -> None:
    client = Mock()
    with pytest.raises((TypeError, ValueError)):
        S3ReplayManifestStore(client, "test-bucket", CODEC).get(version)
    assert client.mock_calls == []


@pytest.mark.parametrize(
    "body", [None, "{}", bytearray(b"{}"), b"{}", b"x" * (MAX_MANIFEST_BYTES + 1)]
)
def test_invalid_body_before_io(body: Any) -> None:
    client = Mock()
    with pytest.raises((TypeError, ValueError)):
        S3ReplayManifestStore(client, "test-bucket", CODEC).put(body)
    assert client.mock_calls == []


@pytest.mark.parametrize("bucket", [None, "", " padded "])
def test_invalid_bucket(bucket: Any) -> None:
    with pytest.raises(ValueError):
        S3ReplayManifestStore(Mock(), bucket, CODEC)


@pytest.mark.parametrize("length", [None, True, -1, "10", MAX_MANIFEST_BYTES + 1])
def test_invalid_length_closes_without_read(length: Any) -> None:
    client = Mock()
    stream = Mock(wraps=BytesIO(b"unread"))
    client.get_object.return_value = {"Body": stream, "ContentLength": length}
    with pytest.raises(ManifestIntegrityError) as error:
        S3ReplayManifestStore(client, "test-bucket", CODEC).get("a" * 64)
    assert isinstance(error.value.__cause__, ValueError)
    stream.read.assert_not_called()
    stream.close.assert_called_once()


@pytest.mark.parametrize(
    "case", ["short", "long", "oversize", "invalid", "noncanonical", "wrong-version", "pin"]
)
def test_corruption_is_not_repaired(case: str) -> None:
    client = Mock()
    body, version = encoded()
    length = len(body)
    if case == "short":
        body = body[:-1]
    elif case == "long":
        body += b"x"
    elif case == "oversize":
        body = b"x" * (MAX_MANIFEST_BYTES + 10)
    elif case == "invalid":
        body = b"x" * length
    elif case == "noncanonical":
        body += b"\n"
        length += 1
    elif case == "wrong-version":
        version = "a" * 64
    else:
        body = body.replace(b'"receipt_sha256":"3', b'"receipt_sha256":"4')
    stream = Mock(wraps=BytesIO(body))
    client.get_object.return_value = {"Body": stream, "ContentLength": length}
    with pytest.raises(ManifestIntegrityError) as error:
        S3ReplayManifestStore(client, "test-bucket", CODEC).get(version)
    assert isinstance(error.value.__cause__, ValueError)
    stream.read.assert_called_once_with(MAX_MANIFEST_BYTES + 1)
    stream.close.assert_called_once()
    client.put_object.assert_not_called()


@pytest.mark.parametrize(
    "code", ["AccessDenied", "NoSuchBucket", "ConditionalRequestConflict", "SlowDown"]
)
def test_service_errors_propagate(code: str) -> None:
    client = Mock()
    failure = service_error(code)
    client.get_object.side_effect = failure
    client.put_object.side_effect = failure
    store = S3ReplayManifestStore(client, "test-bucket", CODEC)
    body, version = encoded()
    with pytest.raises(ClientError) as error:
        store.get(version)
    assert error.value is failure
    with pytest.raises(ClientError) as error:
        store.put(body)
    assert error.value is failure
    assert client.get_object.call_count == client.put_object.call_count == 1


def test_missing_and_disappeared_retry() -> None:
    client = Mock()
    client.get_object.side_effect = service_error("NoSuchKey")
    store = S3ReplayManifestStore(client, "test-bucket", CODEC)
    body, version = encoded()
    assert store.get(version) is None
    client.put_object.side_effect = service_error("PreconditionFailed")
    with pytest.raises(ManifestIntegrityError, match="disappeared"):
        store.put(body)


def test_stream_error_propagates_and_closes() -> None:
    client = Mock()
    stream = Mock()
    failure = OSError("interrupted stream")
    stream.read.side_effect = failure
    client.get_object.return_value = {"Body": stream, "ContentLength": 10}
    with pytest.raises(OSError) as error:
        S3ReplayManifestStore(client, "test-bucket", CODEC).get("a" * 64)
    assert error.value is failure
    stream.close.assert_called_once()


def test_retry_requires_exact_bytes_even_after_integrity_check() -> None:
    client = Mock()
    client.put_object.side_effect = service_error("PreconditionFailed")
    store = S3ReplayManifestStore(client, "test-bucket", CODEC)
    # Inject a hypothetical hash collision at the already-validated get boundary.
    store.get = Mock(return_value=b"other valid bytes")  # type: ignore[method-assign]
    with pytest.raises(ManifestIntegrityError):
        store.put(encoded()[0])
    assert client.put_object.call_count == 1


def test_inclusive_size_limit() -> None:
    value = retained()
    base = len(encoded()[0])
    value = replace(
        value, context_version="x" * (MAX_MANIFEST_BYTES - base + len(value.context_version))
    )
    body = encode_manifest(
        ReplayDatasetManifest(captures=(ManifestCapture(raw=value.raw, candidates=(value,)),)),
        CODEC,
    )
    assert len(body) == MAX_MANIFEST_BYTES
    client = Mock()
    store = S3ReplayManifestStore(client, "test-bucket", CODEC)
    version = store.put(body)
    stream = BytesIO(body)
    client.get_object.return_value = {"Body": stream, "ContentLength": len(body)}
    assert store.get(version) == body
    assert stream.closed


@pytest.mark.parametrize("operation", ["put", "get", "retry"])
def test_transport_failures_propagate_without_retry(operation: str) -> None:
    client = Mock()
    store = S3ReplayManifestStore(client, "test-bucket", CODEC)
    failure = OSError("transport unavailable")
    client.get_object.side_effect = failure
    client.put_object.side_effect = failure
    body, version = encoded()
    if operation == "retry":
        client.put_object.side_effect = service_error("PreconditionFailed")
    with pytest.raises(OSError) as error:
        if operation == "get":
            store.get(version)
        else:
            store.put(body)
    assert error.value is failure
    assert client.put_object.call_count <= 1
    assert client.get_object.call_count <= 1
