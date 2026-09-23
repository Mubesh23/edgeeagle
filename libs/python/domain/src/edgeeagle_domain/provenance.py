"""Independent identities for where data originates and where markets exist."""

from dataclasses import dataclass
from enum import Enum


def _text(value: object, field: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    if not value or value != value.strip():
        raise ValueError(f"{field} must be nonempty and have no surrounding whitespace")


def _capabilities(value: frozenset[str]) -> None:
    if not isinstance(value, frozenset):
        raise TypeError("capabilities must be a frozenset")
    for capability in value:
        _text(capability, "capability")


@dataclass(frozen=True)
class DataSourceId:
    """Opaque internally assigned source identity, not a provider-native ID."""

    value: str

    def __post_init__(self) -> None:
        _text(self.value, "data_source_id")


@dataclass(frozen=True)
class VenueId:
    """Opaque internally assigned venue identity, not a source identity."""

    value: str

    def __post_init__(self) -> None:
        _text(self.value, "venue_id")


class SourceType(Enum):
    SPORTS_DATA = "SPORTS_DATA"
    ODDS_AGGREGATOR = "ODDS_AGGREGATOR"
    VENUE_API = "VENUE_API"
    OFFLINE_DATASET = "OFFLINE_DATASET"


class VenueType(Enum):
    SPORTSBOOK = "SPORTSBOOK"
    PREDICTION_MARKET = "PREDICTION_MARKET"
    EXCHANGE = "EXCHANGE"


@dataclass(frozen=True, kw_only=True)
class DataSource:
    """The system through which data was obtained; not the market operator."""

    data_source_id: DataSourceId
    code: str
    source_type: SourceType
    capabilities: frozenset[str]

    def __post_init__(self) -> None:
        if not isinstance(self.data_source_id, DataSourceId):
            raise TypeError("data_source_id must be a DataSourceId")
        if not isinstance(self.source_type, SourceType):
            raise TypeError("source_type must be a SourceType")
        _text(self.code, "code")
        _capabilities(self.capabilities)


@dataclass(frozen=True, kw_only=True)
class Venue:
    """Where a market or price exists; descriptive metadata, not permission to trade."""

    venue_id: VenueId
    operator: str
    product: str
    jurisdiction: str
    venue_type: VenueType
    capabilities: frozenset[str]

    def __post_init__(self) -> None:
        if not isinstance(self.venue_id, VenueId):
            raise TypeError("venue_id must be a VenueId")
        if not isinstance(self.venue_type, VenueType):
            raise TypeError("venue_type must be a VenueType")
        _text(self.operator, "operator")
        _text(self.product, "product")
        _text(self.jurisdiction, "jurisdiction")
        _capabilities(self.capabilities)
