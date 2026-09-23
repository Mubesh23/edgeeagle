"""Conditional S3 season bundle storage without raw reads (ADR-029)."""

from contextlib import closing
from typing import TYPE_CHECKING

from botocore.exceptions import ClientError

from edgeeagle_ingestion.manifests import EventReceiptCodec
from edgeeagle_ingestion.season_bundle import (
    MAX_PAGE_BYTES,
    SeasonObjectIntegrityError,
    validate_digest,
    validate_object,
)

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


def _key(digest: str) -> str:
    validate_digest(digest)
    return f"snapshots/football-data-seasons/v1/{digest}.json"


class S3SeasonObjectStore:
    """Caller owns the client, finite timeouts/retries, bucket, and retention."""

    def __init__(self, client: "S3Client", bucket: str, codec: EventReceiptCodec) -> None:
        if not isinstance(bucket, str) or not bucket or bucket != bucket.strip():
            raise ValueError("bucket must be nonempty and unpadded")
        self._client = client
        self._bucket = bucket
        self._codec = codec

    def _version(self, body: bytes) -> str:
        return validate_object(body, self._codec)

    def put(self, body: bytes) -> str:
        version = self._version(body)
        key = _key(version)
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=body,
                ContentType="application/json",
                IfNoneMatch="*",
            )
        except ClientError as error:
            if error.response["Error"]["Code"] != "PreconditionFailed":
                raise
            if self.get(version) != body:
                raise SeasonObjectIntegrityError(
                    "existing season object differs or disappeared"
                ) from error
        return version

    def get(self, digest: str) -> bytes | None:
        key = _key(digest)
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as error:
            if error.response["Error"]["Code"] == "NoSuchKey":
                return None
            raise
        with closing(response["Body"]) as stream:
            length = response.get("ContentLength")
            try:
                if type(length) is not int or not 0 <= length <= MAX_PAGE_BYTES:
                    raise ValueError("invalid season object ContentLength")
            except ValueError as error:
                raise SeasonObjectIntegrityError("invalid stored season object length") from error
            # Keep stream/transport errors outside content-error translation.
            body = stream.read(MAX_PAGE_BYTES + 1)
            try:
                if len(body) != length or len(body) > MAX_PAGE_BYTES:
                    raise ValueError("season object body length mismatch")
                if self._version(body) != digest:
                    raise ValueError("season object dataset version mismatch")
            except (TypeError, ValueError) as error:
                raise SeasonObjectIntegrityError("invalid stored season object content") from error
        return body
