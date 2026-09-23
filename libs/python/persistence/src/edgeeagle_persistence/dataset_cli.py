"""Private loopback-only dataset discovery/inspection; never repairs or imports data."""

import argparse
import json
import os
import re
import stat
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import boto3
from botocore.config import Config
from mypy_boto3_s3 import S3Client

from edgeeagle_ingestion.dataset_catalog import CatalogEntry, DatasetCatalog
from edgeeagle_ingestion.manifests import _array, _object, _pairs, _reject_number
from edgeeagle_persistence.raw import S3RawPayloadStore
from edgeeagle_persistence.receipts import EventReceiptCodec
from edgeeagle_persistence.season_storage import S3SeasonObjectStore

MAX_CONFIG_BYTES = 16_384


def decode_catalog(body: bytes) -> tuple[str, DatasetCatalog]:
    if len(body) > MAX_CONFIG_BYTES:
        raise ValueError("catalog configuration exceeds byte limit")
    try:
        model = _object(
            json.loads(
                body.decode(),
                object_pairs_hook=_pairs,
                parse_float=_reject_number,
                parse_constant=_reject_number,
            ),
            {"format", "bucket", "entries"},
        )
        bucket = model["bucket"]
        if type(model["format"]) is not int or model["format"] != 1:
            raise ValueError("unsupported catalog format")
        if not isinstance(bucket, str) or not re.fullmatch(
            r"edgeeagle-(?:private-research|raw-test)-[a-z0-9-]{1,36}", bucket
        ):
            raise ValueError("expected a local research/test bucket")
        entries = tuple(
            CatalogEntry(**_object(entry, {"root_hash", "label"}))
            for entry in _array(model["entries"])
        )
        return bucket, DatasetCatalog(entries)
    except (KeyError, TypeError, ValueError, RecursionError) as error:
        raise ValueError("invalid catalog configuration") from error


def load_catalog(path: Path) -> tuple[str, DatasetCatalog]:
    private = Path.cwd() / ".data"
    if (
        private.is_symlink()
        or path.is_symlink()
        or not path.resolve().is_relative_to(private.resolve())
    ):
        raise ValueError("catalog must be a regular file inside repository .data")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_CONFIG_BYTES:
            raise ValueError("catalog must be a bounded regular file")
        body = stream.read(MAX_CONFIG_BYTES + 1)
    return decode_catalog(body)


def local_client() -> S3Client:
    port = int(os.environ.get("EDGEEAGLE_FLOCI_PORT", "4566"))
    if not 1 <= port <= 65535:
        raise ValueError("invalid local Floci port")
    return boto3.client(
        "s3",
        endpoint_url=f"http://127.0.0.1:{port}",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        aws_session_token="test",
        config=Config(
            s3={"addressing_style": "path"},
            proxies={},
            connect_timeout=3,
            read_timeout=5,
            retries={"max_attempts": 1},
        ),
    )


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError("unsupported catalog output type")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True, type=Path)
    modes = parser.add_subparsers(dest="mode", required=True)
    modes.add_parser("list", help="read root metadata only; does not verify replay")
    inspect = modes.add_parser("inspect", help="freshly verify a cataloged complete capture")
    inspect.add_argument("root_hash")
    args = parser.parse_args(argv)
    try:
        bucket, selected = load_catalog(args.catalog)
        client = local_client()
        try:
            codec = EventReceiptCodec()
            objects = S3SeasonObjectStore(client, bucket, codec)
            if args.mode == "list":
                output = {"items": [asdict(item) for item in selected.list(objects)]}
            else:
                output = asdict(
                    selected.inspect(
                        args.root_hash,
                        codec,
                        objects,
                        S3RawPayloadStore(client, bucket),
                        clock=lambda: datetime.now(UTC),
                    )
                )
            # Materialize and serialize the full result before emitting any success output.
            encoded = json.dumps(output, default=_json_default, indent=2, sort_keys=True)
        finally:
            client.close()
        print(encoded)
        return 0
    except Exception as error:
        # Backend exceptions may include transport configuration or private object names.
        print(f"Dataset catalog operation failed ({type(error).__name__}).", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
