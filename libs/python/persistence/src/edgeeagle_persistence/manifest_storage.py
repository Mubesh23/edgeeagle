"""Conditional S3 replay manifest storage without raw reads (ADR-027)."""

import json
import re
from contextlib import closing
from typing import TYPE_CHECKING, cast

from botocore.exceptions import ClientError

from edgeeagle_ingestion.manifest_storage import ManifestIntegrityError
from edgeeagle_ingestion.manifests import MAX_MANIFEST_BYTES, EventReceiptCodec, decode_manifest

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


def _key(dataset_version: str) -> str:
    if not isinstance(dataset_version, str):
        raise TypeError("dataset_version must be a string")
    if re.fullmatch(r"[0-9a-f]{64}", dataset_version) is None:
        raise ValueError("dataset_version must be a lowercase SHA-256 digest")
    return f"snapshots/replay-manifests/v1/{dataset_version}.json"


class S3ReplayManifestStore:
    """Caller owns the client, finite timeouts/retries, bucket, and retention."""

    def __init__(self, client: "S3Client", bucket: str, codec: EventReceiptCodec) -> None:
        if not isinstance(bucket, str) or not bucket or bucket != bucket.strip():
            raise ValueError("bucket must be nonempty and unpadded")
        self._client = client
        self._bucket = bucket
        self._codec = codec

    def _version(self, body: bytes) -> str:
        decode_manifest(body, self._codec)
        # Only extract identity after the existing codec has verified every pin
        # and canonical byte. Do not invent a second serialization/hash recipe.
        return cast(str, json.loads(body)["dataset_version"])

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
                raise ManifestIntegrityError("existing manifest differs or disappeared") from error
        return version

    def get(self, dataset_version: str) -> bytes | None:
        key = _key(dataset_version)
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as error:
            if error.response["Error"]["Code"] == "NoSuchKey":
                return None
            raise
        with closing(response["Body"]) as stream:
            length = response.get("ContentLength")
            try:
                if type(length) is not int or not 0 <= length <= MAX_MANIFEST_BYTES:
                    raise ValueError("invalid manifest ContentLength")
            except ValueError as error:
                raise ManifestIntegrityError("invalid stored manifest length") from error
            # Keep stream/transport errors outside content-error translation.
            body = stream.read(MAX_MANIFEST_BYTES + 1)
            try:
                if len(body) != length or len(body) > MAX_MANIFEST_BYTES:
                    raise ValueError("manifest body length mismatch")
                if self._version(body) != dataset_version:
                    raise ValueError("manifest dataset version mismatch")
            except (TypeError, ValueError) as error:
                raise ManifestIntegrityError("invalid stored manifest content") from error
        return body
