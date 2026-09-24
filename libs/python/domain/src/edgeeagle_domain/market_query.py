"""Bounded observation reads, not executable prices or historical research snapshots."""

from dataclasses import dataclass
from typing import Literal, Protocol

from edgeeagle_domain._validation import instance
from edgeeagle_domain.markets import Market, MarketId, Quote, QuoteId, Selection
from edgeeagle_domain.raw import RawPayloadReference
from edgeeagle_domain.sports import EventId


def _limit(value: int) -> None:
    if type(value) is not int or not 1 <= value <= 100:
        raise ValueError("limit must be an integer in [1, 100]")


@dataclass(frozen=True, kw_only=True)
class MarketQuery:
    limit: int = 50
    after_market_id: MarketId | None = None

    def __post_init__(self) -> None:
        _limit(self.limit)
        if self.after_market_id is not None:
            instance(self.after_market_id, MarketId, "after_market_id")


@dataclass(frozen=True, kw_only=True)
class QuoteQuery:
    limit: int = 50
    after_quote_id: QuoteId | None = None

    def __post_init__(self) -> None:
        _limit(self.limit)
        if self.after_quote_id is not None:
            instance(self.after_quote_id, QuoteId, "after_quote_id")


@dataclass(frozen=True)
class MarketView:
    market: Market
    selections: tuple[Selection, ...]


@dataclass(frozen=True, kw_only=True)
class QuoteObservation:
    quote: Quote
    market_id: MarketId
    receipt_id: str
    raw: RawPayloadReference
    provider_event_id: str
    provider_bookmaker_key: str
    provider_market_key: str
    provider_outcome_label: str
    parser_version: str
    normalizer_version: str
    context_version: str
    usage: Literal["SYNTHETIC_ONLY"]


@dataclass(frozen=True)
class MarketPage:
    items: tuple[MarketView, ...]
    next_after_market_id: MarketId | None


@dataclass(frozen=True)
class QuotePage:
    items: tuple[QuoteObservation, ...]
    next_after_quote_id: QuoteId | None


class MarketReader(Protocol):
    """One caller-owned read-only snapshot; None means the parent does not exist.

    Pages sort by canonical ID, not time, with exclusive continuation. Independent
    requests do not form a pinned dataset. Existing parents can have empty pages.
    """

    def list_markets(self, event_id: EventId, query: MarketQuery) -> MarketPage | None: ...

    def list_quotes(self, market_id: MarketId, query: QuoteQuery) -> QuotePage | None: ...
