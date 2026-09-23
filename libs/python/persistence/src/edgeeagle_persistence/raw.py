"""Conditional, content-addressed S3 storage (ADR-015)."""

import hashlib
import json
from typing import TYPE_CHECKING
from urllib.parse import quote

from botocore.exceptions import ClientError

from edgeeagle_domain.raw import RawPayload, RawPayloadIntegrityError, RawPayloadReference

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


def _location(reference: RawPayloadReference) -> tuple[str, dict[str, str]]:
    if not isinstance(reference, RawPayloadReference):
        raise TypeError("reference must be a RawPayloadReference")
    capture = reference.capture
    descriptor = json.dumps(
        {
            "version": 1,
            "data_source_id": capture.data_source_id.value,
            "resource": capture.resource,
            **{
                field: value.isoformat() if value is not None else None
                for field in ("ingested_at", "effective_at", "observed_at", "available_at")
                for value in (getattr(capture, field),)
            },
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    if len(descriptor.encode("ascii")) > 1500:
        raise ValueError("capture descriptor exceeds 1500 bytes")
    digest = hashlib.sha256(descriptor.encode("ascii")).hexdigest()
    key = (
        f"raw/v1/source={quote(capture.data_source_id.value, safe='')}/"
        f"resource={quote(capture.resource, safe='')}/date={capture.ingested_at.date()}/"
        f"{digest}/{reference.sha256}.bin"
    )
    if len(key.encode("utf-8")) > 1024:
        raise ValueError("raw object key exceeds 1024 bytes")
    return key, {
        "capture": descriptor,
        "sha256": reference.sha256,
        "size-bytes": str(reference.size_bytes),
    }


class S3RawPayloadStore:
    """Caller owns client, timeouts/retries, bucket lifecycle, and retention rights."""

    def __init__(self, client: "S3Client", bucket: str) -> None:
        if not isinstance(bucket, str) or not bucket or bucket != bucket.strip():
            raise ValueError("bucket must be nonempty and unpadded")
        self._client = client
        self._bucket = bucket

    def put(self, payload: RawPayload) -> RawPayloadReference:
        if not isinstance(payload, RawPayload):
            raise TypeError("payload must be a RawPayload")
        reference = payload.reference()
        key, metadata = _location(reference)
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=payload.body,
                Metadata=metadata,
                ContentType="application/octet-stream",
                IfNoneMatch="*",
            )
        except ClientError as error:
            if error.response["Error"]["Code"] != "PreconditionFailed":
                raise
            if self.get(reference) != payload.body:
                raise RawPayloadIntegrityError(
                    "existing raw capture differs or disappeared"
                ) from error
        return reference

    def get(self, reference: RawPayloadReference) -> bytes | None:
        key, metadata = _location(reference)
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as error:
            if error.response["Error"]["Code"] == "NoSuchKey":
                return None
            raise
        with response["Body"] as stream:
            body = stream.read(reference.size_bytes + 1)
        if (
            response.get("Metadata") != metadata
            or len(body) != reference.size_bytes
            or hashlib.sha256(body).hexdigest() != reference.sha256
        ):
            raise RawPayloadIntegrityError("raw capture checksum, size, or provenance mismatch")
        return body
