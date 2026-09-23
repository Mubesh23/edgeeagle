from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from io import BytesIO
from unittest.mock import Mock

import pytest
from botocore.exceptions import ClientError

from edgeeagle_domain.provenance import DataSourceId
from edgeeagle_domain.raw import RawCapture, RawPayload, RawPayloadIntegrityError
from edgeeagle_persistence.raw import S3RawPayloadStore


def payload() -> RawPayload:
    return RawPayload(
        capture=RawCapture(
            data_source_id=DataSourceId("synthetic"),
            resource="odds",
            ingested_at=datetime(2026, 9, 22, tzinfo=UTC),
        ),
        body=b"\x00\xffraw",
    )


def test_conditional_write_and_verified_read() -> None:
    client = Mock()
    store = S3RawPayloadStore(client, "test-bucket")
    raw = payload()
    reference = store.put(raw)
    arguments = client.put_object.call_args.kwargs
    assert arguments["IfNoneMatch"] == "*"
    assert arguments["Body"] == raw.body
    client.get_object.return_value = {"Body": BytesIO(raw.body), "Metadata": arguments["Metadata"]}
    assert store.get(reference) == raw.body
    client.put_object.side_effect = ClientError(
        {"Error": {"Code": "PreconditionFailed"}}, "PutObject"
    )
    client.get_object.return_value = {"Body": BytesIO(raw.body), "Metadata": arguments["Metadata"]}
    assert store.put(raw) == reference
    client.get_object.return_value = {
        "Body": BytesIO(b"corrupt"),
        "Metadata": arguments["Metadata"],
    }
    with pytest.raises(RawPayloadIntegrityError):
        store.get(reference)


@pytest.mark.parametrize("code", ["AccessDenied", "NoSuchBucket", "ConditionalRequestConflict"])
def test_service_errors_are_not_absence_or_success(code: str) -> None:
    client = Mock()
    client.get_object.side_effect = ClientError({"Error": {"Code": code}}, "GetObject")
    client.put_object.side_effect = ClientError({"Error": {"Code": code}}, "PutObject")
    store = S3RawPayloadStore(client, "test-bucket")
    with pytest.raises(ClientError):
        store.get(payload().reference())
    with pytest.raises(ClientError):
        store.put(payload())


def test_missing_and_disappeared_replay() -> None:
    client = Mock()
    client.get_object.side_effect = ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
    store = S3RawPayloadStore(client, "test-bucket")
    assert store.get(payload().reference()) is None
    client.put_object.side_effect = ClientError(
        {"Error": {"Code": "PreconditionFailed"}}, "PutObject"
    )
    with pytest.raises(RawPayloadIntegrityError, match="disappeared"):
        store.put(payload())


@pytest.mark.parametrize("change", ["metadata", "size", "checksum"])
def test_integrity_checks_close_response_body(change: str) -> None:
    client = Mock()
    store = S3RawPayloadStore(client, "test-bucket")
    reference = store.put(payload())
    metadata = client.put_object.call_args.kwargs["Metadata"].copy()
    body = payload().body
    if change == "metadata":
        metadata["capture"] = "{}"
    elif change == "size":
        body += b"extra"
    else:
        body = b"x" * len(body)
    stream = BytesIO(body)
    client.get_object.return_value = {"Body": stream, "Metadata": metadata}
    with pytest.raises(RawPayloadIntegrityError):
        store.get(reference)
    assert stream.closed


def test_validation_precedes_io_and_timezone_identity() -> None:
    client = Mock()
    with pytest.raises(ValueError):
        S3RawPayloadStore(client, " ")
    store = S3RawPayloadStore(client, "test-bucket")
    with pytest.raises(TypeError):
        store.put(None)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        store.get(None)  # type: ignore[arg-type]
    for resource, message in [("x" * 1600, "descriptor"), ("/" * 300, "key")]:
        with pytest.raises(ValueError, match=message):
            store.put(replace(payload(), capture=replace(payload().capture, resource=resource)))
    client.put_object.assert_not_called()
    raw = payload()
    store.put(raw)
    first = client.put_object.call_args
    offset = raw.capture.ingested_at.astimezone(timezone(timedelta(hours=-5)))
    store.put(replace(raw, capture=replace(raw.capture, ingested_at=offset)))
    assert client.put_object.call_args == first
    store.put(replace(raw, body=b"different"))
    assert client.put_object.call_args.kwargs["Key"] != first.kwargs["Key"]
