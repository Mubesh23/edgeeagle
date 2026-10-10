"""Read-only HTTP projection for provider-native binary order-book evidence."""

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, HTTPException, Path, Request
from pydantic import AfterValidator, BaseModel

from edgeeagle_domain._validation import text
from edgeeagle_domain.raw import RawPayloadIntegrityError
from edgeeagle_ingestion.kalshi_orderbook import KalshiOrderBookCandidate

OrderBookReads = Callable[[str, str], KalshiOrderBookCandidate | None]


def _canonical_text(value: str) -> str:
    text(value, "identifier")
    if "\x00" in value:
        raise ValueError("NUL is not supported")
    return value


CanonicalText = Annotated[str, AfterValidator(_canonical_text)]


class OrderBookLevelResponse(BaseModel):
    price_dollars: str
    contract_count: str


class RawOrderBookReferenceResponse(BaseModel):
    sha256: str
    size_bytes: int
    resource: str
    ingested_at: datetime
    effective_at: datetime | None
    observed_at: datetime | None
    available_at: datetime | None


class ProviderOrderBookResponse(BaseModel):
    data_source_id: str
    venue_id: str
    market_ticker: str
    snapshot_at: datetime
    historical_availability: Literal["UNKNOWN"]
    mapping_status: Literal["UNMAPPED"]
    usage: Literal["SYNTHETIC_ONLY"]
    parser_version: str
    normalizer_version: str
    raw: RawOrderBookReferenceResponse
    yes_bids: list[OrderBookLevelResponse]
    no_bids: list[OrderBookLevelResponse]

    @classmethod
    def from_candidate(cls, value: KalshiOrderBookCandidate) -> "ProviderOrderBookResponse":
        raw = value.raw
        capture = raw.capture
        return cls(
            data_source_id=value.data_source_id.value,
            venue_id=value.venue_id.value,
            market_ticker=value.market_ticker,
            snapshot_at=value.snapshot_at,
            historical_availability="UNKNOWN",
            mapping_status="UNMAPPED",
            usage="SYNTHETIC_ONLY",
            parser_version=value.parser_version,
            normalizer_version=value.normalizer_version,
            raw=RawOrderBookReferenceResponse(
                sha256=raw.sha256,
                size_bytes=raw.size_bytes,
                resource=capture.resource,
                ingested_at=capture.ingested_at,
                effective_at=capture.effective_at,
                observed_at=capture.observed_at,
                available_at=capture.available_at,
            ),
            yes_bids=[
                OrderBookLevelResponse(
                    price_dollars=str(level.price_dollars),
                    contract_count=str(level.contract_count),
                )
                for level in value.order_book.yes_bids
            ],
            no_bids=[
                OrderBookLevelResponse(
                    price_dollars=str(level.price_dollars),
                    contract_count=str(level.contract_count),
                )
                for level in value.order_book.no_bids
            ],
        )


class OrderBookErrorResponse(BaseModel):
    detail: str


router = APIRouter()


@router.get(
    "/v1/provider-order-books/{dataSourceId}/{marketTicker}",
    response_model=ProviderOrderBookResponse,
    operation_id="get_provider_order_book",
    responses={
        404: {"model": OrderBookErrorResponse},
        503: {"model": OrderBookErrorResponse},
    },
)
def get_provider_order_book(
    request: Request,
    data_source_id: Annotated[
        CanonicalText, Path(alias="dataSourceId", min_length=1, max_length=128)
    ],
    market_ticker: Annotated[
        str,
        Path(
            alias="marketTicker",
            min_length=1,
            max_length=128,
            pattern=r"^[A-Z0-9][A-Z0-9_-]{0,127}$",
        ),
    ],
) -> ProviderOrderBookResponse:
    reads = cast(OrderBookReads | None, request.app.state.orderbook_reads)
    if reads is None:
        raise HTTPException(503, "Provider order-book reads are not configured")
    try:
        candidate = reads(data_source_id, market_ticker)
    except (FileNotFoundError, ValueError, RawPayloadIntegrityError) as error:
        raise HTTPException(
            503, "Retained provider order book is unavailable or invalid"
        ) from error
    if candidate is None:
        raise HTTPException(404, "Provider order book not found")
    return ProviderOrderBookResponse.from_candidate(candidate)
