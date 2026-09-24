"""HTTP serialization of retained observations, never pricing or execution advice."""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from datetime import datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, HTTPException, Path, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import OperationalError, TimeoutError

from edgeeagle_api.events import CanonicalText
from edgeeagle_domain.market_query import (
    MarketQuery,
    MarketReader,
    MarketView,
    QuoteObservation,
    QuoteQuery,
)
from edgeeagle_domain.markets import MarketId, MarketPeriod, MarketType, Outcome, QuoteId
from edgeeagle_domain.sports import EventId

MarketReads = Callable[[], AbstractContextManager[MarketReader]]


class MarketSelectionResponse(BaseModel):
    selection_id: str
    outcome: Outcome
    participant_id: str | None


class MarketResponse(BaseModel):
    market_id: str
    event_id: str
    market_type: MarketType
    period: MarketPeriod
    selections: list[MarketSelectionResponse]

    @classmethod
    def from_view(cls, value: MarketView) -> "MarketResponse":
        return cls(
            market_id=value.market.market_id.value,
            event_id=value.market.event_id.value,
            market_type=value.market.market_type,
            period=value.market.period,
            selections=[
                MarketSelectionResponse(
                    selection_id=s.selection_id.value,
                    outcome=s.outcome,
                    participant_id=s.participant_id.value if s.participant_id else None,
                )
                for s in value.selections
            ],
        )


class MarketListResponse(BaseModel):
    items: list[MarketResponse]
    next_after_market_id: str | None


class QuoteCaptureResponse(BaseModel):
    data_source_id: str
    resource: str
    ingested_at: datetime
    effective_at: datetime | None
    observed_at: datetime | None
    available_at: datetime | None


class QuoteRawReferenceResponse(BaseModel):
    capture: QuoteCaptureResponse
    sha256: str
    size_bytes: int


class QuoteProvenanceResponse(BaseModel):
    receipt_id: str
    raw: QuoteRawReferenceResponse
    provider_event_id: str
    provider_bookmaker_key: str
    provider_market_key: str
    provider_outcome_label: str
    parser_version: str
    normalizer_version: str
    context_version: str
    usage: Literal["SYNTHETIC_ONLY"]


class QuoteResponse(BaseModel):
    quote_id: str
    market_id: str
    selection_id: str
    data_source_id: str
    venue_id: str
    odds_decimal: str = Field(
        description="Exact decimal observation, encoded as a string; not an executable price."
    )
    ingested_at: datetime
    observed_at: datetime | None
    available_at: datetime | None
    effective_at: datetime | None
    provider_quote_id: str | None
    provenance: QuoteProvenanceResponse

    @classmethod
    def from_observation(cls, value: QuoteObservation) -> "QuoteResponse":
        quote, capture = value.quote, value.raw.capture
        return cls(
            quote_id=quote.quote_id.value,
            market_id=value.market_id.value,
            selection_id=quote.selection_id.value,
            data_source_id=quote.data_source_id.value,
            venue_id=quote.venue_id.value,
            odds_decimal=str(quote.odds_decimal),
            ingested_at=quote.ingested_at,
            observed_at=quote.observed_at,
            available_at=quote.available_at,
            effective_at=quote.effective_at,
            provider_quote_id=quote.provider_quote_id,
            provenance=QuoteProvenanceResponse(
                receipt_id=value.receipt_id,
                raw=QuoteRawReferenceResponse(
                    sha256=value.raw.sha256,
                    size_bytes=value.raw.size_bytes,
                    capture=QuoteCaptureResponse(
                        data_source_id=capture.data_source_id.value,
                        resource=capture.resource,
                        ingested_at=capture.ingested_at,
                        observed_at=capture.observed_at,
                        available_at=capture.available_at,
                        effective_at=capture.effective_at,
                    ),
                ),
                provider_event_id=value.provider_event_id,
                provider_bookmaker_key=value.provider_bookmaker_key,
                provider_market_key=value.provider_market_key,
                provider_outcome_label=value.provider_outcome_label,
                parser_version=value.parser_version,
                normalizer_version=value.normalizer_version,
                context_version=value.context_version,
                usage=value.usage,
            ),
        )


class QuoteListResponse(BaseModel):
    items: list[QuoteResponse]
    next_after_quote_id: str | None


class MarketErrorResponse(BaseModel):
    detail: str


@contextmanager
def market_reader(request: Request) -> Iterator[MarketReader]:
    factory = cast(MarketReads | None, request.app.state.market_reads)
    if factory is None:
        raise HTTPException(503, "Market reads are not configured")
    try:
        with factory() as reader:
            yield reader
    except (OperationalError, TimeoutError) as error:
        raise HTTPException(503, "Market data is temporarily unavailable") from error


router = APIRouter()


@router.get(
    "/v1/events/{eventId}/markets",
    response_model=MarketListResponse,
    operation_id="list_event_markets",
    responses={404: {"model": MarketErrorResponse}, 503: {"model": MarketErrorResponse}},
)
def list_event_markets(
    request: Request,
    event_id: Annotated[CanonicalText, Path(alias="eventId")],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    after_market_id: Annotated[CanonicalText | None, Query()] = None,
) -> MarketListResponse:
    """Canonical-ID pages; independent requests do not form a frozen dataset."""
    query = MarketQuery(
        limit=limit,
        after_market_id=MarketId(after_market_id) if after_market_id is not None else None,
    )
    with market_reader(request) as reader:
        page = reader.list_markets(EventId(event_id), query)
        if page is None:
            raise HTTPException(404, "Event not found")
        return MarketListResponse(
            items=[MarketResponse.from_view(item) for item in page.items],
            next_after_market_id=page.next_after_market_id.value
            if page.next_after_market_id
            else None,
        )


@router.get(
    "/v1/markets/{marketId}/quotes",
    response_model=QuoteListResponse,
    operation_id="list_market_quotes",
    responses={404: {"model": MarketErrorResponse}, 503: {"model": MarketErrorResponse}},
)
def list_market_quotes(
    request: Request,
    market_id: Annotated[CanonicalText, Path(alias="marketId")],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    after_quote_id: Annotated[CanonicalText | None, Query()] = None,
) -> QuoteListResponse:
    """Synthetic retained observations in ID order, not latest prices or historical as-of data."""
    query = QuoteQuery(
        limit=limit, after_quote_id=QuoteId(after_quote_id) if after_quote_id is not None else None
    )
    with market_reader(request) as reader:
        page = reader.list_quotes(MarketId(market_id), query)
        if page is None:
            raise HTTPException(404, "Market not found")
        return QuoteListResponse(
            items=[QuoteResponse.from_observation(item) for item in page.items],
            next_after_quote_id=page.next_after_quote_id.value
            if page.next_after_quote_id
            else None,
        )
