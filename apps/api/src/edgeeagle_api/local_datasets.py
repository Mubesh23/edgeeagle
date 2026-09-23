"""Explicit private catalog composition; bind only to loopback, never host publicly."""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI

from edgeeagle_api.datasets import CatalogAccess
from edgeeagle_api.main import create_app
from edgeeagle_persistence.dataset_cli import load_catalog, local_client
from edgeeagle_persistence.raw import S3RawPayloadStore
from edgeeagle_persistence.receipts import EventReceiptCodec
from edgeeagle_persistence.season_storage import S3SeasonObjectStore


def create_local_dataset_app() -> FastAPI:
    """Load explicit pins once, open/close local storage clients per read request."""
    path = os.environ.get("EDGEEAGLE_DATASET_CATALOG", "")
    if not path:
        raise ValueError("Supply EDGEEAGLE_DATASET_CATALOG inside repository .data")
    bucket, selected = load_catalog(Path(path))

    @contextmanager
    def reads() -> Iterator[CatalogAccess]:
        client = local_client()
        try:
            codec = EventReceiptCodec()
            yield CatalogAccess(
                selected,
                S3SeasonObjectStore(client, bucket, codec),
                S3RawPayloadStore(client, bucket),
                codec,
                lambda: datetime.now(UTC),
            )
        finally:
            client.close()

    return create_app(dataset_reads=reads)
