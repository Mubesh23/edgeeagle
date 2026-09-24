"""Canonical market semantics and quote observations; no pricing or execution policy."""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum

from edgeeagle_domain._validation import aware_datetime, instance, text
from edgeeagle_domain.provenance import DataSourceId, VenueId
from edgeeagle_domain.sports import EventId, EventParticipant, ParticipantId


@dataclass(frozen=True)
class MarketId:
    value: str

    def __post_init__(self) -> None:
        text(self.value, "market_id")


@dataclass(frozen=True)
class SelectionId:
    value: str

    def __post_init__(self) -> None:
        text(self.value, "selection_id")


@dataclass(frozen=True)
class QuoteId:
    """Observation identity allocated by versioned ingestion, not a provider ID."""

    value: str

    def __post_init__(self) -> None:
        text(self.value, "quote_id")


class MarketType(Enum):
    RESULT_3WAY = "RESULT_3WAY"


class MarketPeriod(Enum):
    REGULATION_TIME = "REGULATION_TIME"


class Outcome(Enum):
    HOME = "HOME"
    DRAW = "DRAW"
    AWAY = "AWAY"


def _identity(fields: dict[str, str | int]) -> str:
    body = json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(body.encode("ascii")).hexdigest()


@dataclass(frozen=True, kw_only=True)
class Market:
    """Initial three-way regulation-result definition, independent of source/venue."""

    event_id: EventId
    market_type: MarketType
    period: MarketPeriod

    def __post_init__(self) -> None:
        instance(self.event_id, EventId, "event_id")
        instance(self.market_type, MarketType, "market_type")
        instance(self.period, MarketPeriod, "period")

    @property
    def market_id(self) -> MarketId:
        return MarketId(
            _identity(
                {
                    "identity_version": 1,
                    "event_id": self.event_id.value,
                    "market_type": self.market_type.value,
                    "period": self.period.value,
                }
            )
        )


@dataclass(frozen=True, kw_only=True)
class Selection:
    market_id: MarketId
    outcome: Outcome
    participant_id: ParticipantId | None

    def __post_init__(self) -> None:
        instance(self.market_id, MarketId, "market_id")
        instance(self.outcome, Outcome, "outcome")
        if self.participant_id is not None:
            instance(self.participant_id, ParticipantId, "participant_id")
        if (self.outcome is Outcome.DRAW) != (self.participant_id is None):
            raise ValueError("DRAW requires no participant; HOME/AWAY require a participant")

    @property
    def selection_id(self) -> SelectionId:
        return SelectionId(
            _identity(
                {
                    "identity_version": 1,
                    "market_id": self.market_id.value,
                    "outcome": self.outcome.value,
                }
            )
        )


def validate_market_selections(
    market: Market,
    selections: tuple[Selection, ...],
    entries: tuple[EventParticipant, ...],
) -> None:
    """Validate complete three-way membership; caller separately proves soccer context."""
    instance(market, Market, "market")
    instance(selections, tuple, "selections")
    instance(entries, tuple, "entries")
    if len(selections) != 3 or len(entries) != 2:
        raise ValueError("three-way markets require three selections and two event entries")
    for entry in entries:
        instance(entry, EventParticipant, "entry")
        if entry.event_id != market.event_id:
            raise ValueError("entry belongs to another event")
    if {e.role for e in entries} != {"HOME", "AWAY"} or len(
        {e.participant_id for e in entries}
    ) != 2:
        raise ValueError("event requires distinct HOME/AWAY participants")
    expected = {e.role: e.participant_id for e in entries}
    seen = set()
    for selection in selections:
        instance(selection, Selection, "selection")
        if selection.market_id != market.market_id:
            raise ValueError("selection belongs to another market")
        if selection.outcome in seen:
            raise ValueError("duplicate selection outcome")
        seen.add(selection.outcome)
        if selection.participant_id != expected.get(selection.outcome.value):
            raise ValueError("selection participant differs from event role")


@dataclass(frozen=True, kw_only=True)
class Quote:
    """Immutable observed decimal price; not freshness, availability evidence or a fill."""

    quote_id: QuoteId
    selection_id: SelectionId
    data_source_id: DataSourceId
    venue_id: VenueId
    odds_decimal: Decimal
    ingested_at: datetime
    observed_at: datetime | None = None
    available_at: datetime | None = None
    effective_at: datetime | None = None
    provider_quote_id: str | None = None

    def __post_init__(self) -> None:
        instance(self.quote_id, QuoteId, "quote_id")
        instance(self.selection_id, SelectionId, "selection_id")
        instance(self.data_source_id, DataSourceId, "data_source_id")
        instance(self.venue_id, VenueId, "venue_id")
        instance(self.odds_decimal, Decimal, "odds_decimal")
        if not self.odds_decimal.is_finite() or self.odds_decimal <= 1:
            raise ValueError("odds_decimal must be finite and greater than one")
        aware_datetime(self.ingested_at, "ingested_at")
        for name in ("ingested_at", "observed_at", "available_at", "effective_at"):
            value = getattr(self, name)
            if value is not None:
                aware_datetime(value, name)
                object.__setattr__(self, name, value.astimezone(UTC))
        if self.available_at is not None and self.available_at > self.ingested_at:
            raise ValueError("availability must not exceed ingestion time")
        if self.provider_quote_id is not None:
            text(self.provider_quote_id, "provider_quote_id")
