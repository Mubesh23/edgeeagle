"""HTTP consumer of the authoritative, read-only retained catalog (ADR-032)."""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, cast

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, HTTPException, Path, Request
from pydantic import BaseModel

from edgeeagle_domain.raw import RawPayloadIntegrityError, RawPayloadStore
from edgeeagle_ingestion.dataset_catalog import DatasetCatalog, DatasetInspection, DatasetListing
from edgeeagle_ingestion.manifests import EventReceiptCodec
from edgeeagle_ingestion.season_bundle import SeasonObjectStore


@dataclass(frozen=True)
class CatalogAccess:
    catalog: DatasetCatalog
    objects: SeasonObjectStore
    raw_store: RawPayloadStore
    codec: EventReceiptCodec
    clock: Callable[[], datetime]


DatasetReads = Callable[[], AbstractContextManager[CatalogAccess]]


class DatasetListResponse(BaseModel):
    items: list[DatasetListing]


class DatasetErrorResponse(BaseModel):
    detail: str


@contextmanager
def catalog_access(request: Request) -> Iterator[CatalogAccess]:
    factory = cast(DatasetReads | None, request.app.state.dataset_reads)
    if factory is None:
        raise HTTPException(503, "Dataset reads are not configured")
    try:
        with factory() as access:
            yield access
    except (
        FileNotFoundError,
        ValueError,
        RawPayloadIntegrityError,
        BotoCoreError,
        ClientError,
    ) as error:
        raise HTTPException(
            503, "Retained dataset is unavailable or failed verification"
        ) from error


router = APIRouter()


@router.get(
    "/v1/datasets",
    response_model=DatasetListResponse,
    operation_id="list_datasets",
    responses={503: {"model": DatasetErrorResponse}},
)
def list_datasets(request: Request) -> DatasetListResponse:
    """Read selected roots only; never imply that full replay was checked."""
    with catalog_access(request) as access:
        return DatasetListResponse(items=list(access.catalog.list(access.objects)))


@router.get(
    "/v1/datasets/{rootHash}/inspection",
    response_model=DatasetInspection,
    operation_id="inspect_dataset",
    responses={404: {"model": DatasetErrorResponse}, 503: {"model": DatasetErrorResponse}},
)
def inspect_dataset(
    request: Request,
    root_hash: Annotated[
        str, Path(alias="rootHash", min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    ],
) -> DatasetInspection:
    """Freshly replay retained artifacts; never upgrade historical eligibility."""
    with catalog_access(request) as access:
        if not any(entry.root_hash == root_hash for entry in access.catalog.entries):
            raise HTTPException(404, "Dataset not selected")
        return access.catalog.inspect(
            root_hash, access.codec, access.objects, access.raw_store, clock=access.clock
        )
