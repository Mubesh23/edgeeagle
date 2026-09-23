"""Source and venue identity remain independent, even for the same operator."""

from dataclasses import FrozenInstanceError, replace
from typing import Any, cast

import pytest

from edgeeagle_domain.provenance import (
    DataSource,
    DataSourceId,
    SourceType,
    Venue,
    VenueId,
    VenueType,
)


@pytest.fixture
def source() -> DataSource:
    return DataSource(
        data_source_id=DataSourceId("source-1"),
        code="THE_ODDS_API",
        source_type=SourceType.ODDS_AGGREGATOR,
        capabilities=frozenset({"market_data"}),
    )


@pytest.fixture
def venue() -> Venue:
    return Venue(
        venue_id=VenueId("venue-1"),
        operator="Bovada",
        product="Synthetic sportsbook",
        jurisdiction="fixture-only",
        venue_type=VenueType.SPORTSBOOK,
        capabilities=frozenset(),
    )


def test_aggregator_is_not_the_venue(source: DataSource, venue: Venue) -> None:
    assert source.code == "THE_ODDS_API"
    assert venue.operator == "Bovada"
    assert cast(object, source.data_source_id) != venue.venue_id


@pytest.mark.parametrize("operator", ["Kalshi", "Polymarket"])
def test_operator_can_have_both_roles(source: DataSource, venue: Venue, operator: str) -> None:
    feed = replace(source, code=f"{operator.upper()}_API", source_type=SourceType.VENUE_API)
    market = replace(venue, operator=operator, venue_type=VenueType.PREDICTION_MARKET)
    assert feed.capabilities == frozenset({"market_data"})
    assert market.capabilities == frozenset()


def test_identifiers_are_distinct_value_types() -> None:
    assert DataSourceId("same") == DataSourceId("same")
    assert VenueId("same") == VenueId("same")
    # Erase the static type to exercise the runtime boundary too.
    assert cast(object, DataSourceId("same")) != VenueId("same")
    assert len({DataSourceId("same"), VenueId("same")}) == 2


@pytest.mark.parametrize("identifier", [DataSourceId, VenueId])
@pytest.mark.parametrize("value", ["", " ", " padded", "trailing "])
def test_identifiers_reject_blank_or_padded_values(
    identifier: type[DataSourceId] | type[VenueId], value: str
) -> None:
    with pytest.raises(ValueError):
        identifier(value)


@pytest.mark.parametrize("identifier", [DataSourceId, VenueId])
@pytest.mark.parametrize("value", [None, 1, True])
def test_identifiers_do_not_coerce_types(
    identifier: type[DataSourceId] | type[VenueId], value: Any
) -> None:
    with pytest.raises(TypeError):
        identifier(value)


@pytest.mark.parametrize(
    "changes,error",
    [
        ({"data_source_id": VenueId("source-1")}, TypeError),
        ({"data_source_id": "source-1"}, TypeError),
        ({"source_type": "ODDS_AGGREGATOR"}, TypeError),
        ({"code": ""}, ValueError),
        ({"code": " THE_ODDS_API"}, ValueError),
        ({"code": None}, TypeError),
        ({"capabilities": {"market_data"}}, TypeError),
        ({"capabilities": "market_data"}, TypeError),
        ({"capabilities": frozenset({""})}, ValueError),
        ({"capabilities": frozenset({1})}, TypeError),
    ],
)
def test_source_rejects_invalid_fields(
    source: DataSource, changes: dict[str, Any], error: type[Exception]
) -> None:
    with pytest.raises(error):
        replace(source, **changes)


@pytest.mark.parametrize(
    "changes,error",
    [
        ({"venue_id": DataSourceId("venue-1")}, TypeError),
        ({"venue_id": "venue-1"}, TypeError),
        ({"venue_type": "SPORTSBOOK"}, TypeError),
        ({"operator": ""}, ValueError),
        ({"product": " "}, ValueError),
        ({"jurisdiction": ""}, ValueError),
        ({"jurisdiction": None}, TypeError),
        ({"capabilities": []}, TypeError),
        ({"capabilities": frozenset({" padded "})}, ValueError),
    ],
)
def test_venue_rejects_invalid_fields(
    venue: Venue, changes: dict[str, Any], error: type[Exception]
) -> None:
    with pytest.raises(error):
        replace(venue, **changes)


def test_records_and_ids_are_immutable(source: DataSource, venue: Venue) -> None:
    for record, field in [
        (source, "code"),
        (venue, "operator"),
        (source.data_source_id, "value"),
        (venue.venue_id, "value"),
    ]:
        with pytest.raises(FrozenInstanceError):
            setattr(record, field, "changed")
    assert hash(source) == hash(replace(source))
    assert hash(venue) == hash(replace(venue))


def test_source_catalog_is_not_a_domain_enum(source: DataSource) -> None:
    assert replace(source, code="FUTURE_SOURCE").code == "FUTURE_SOURCE"


@pytest.mark.parametrize("source_type", list(SourceType))
def test_all_documented_source_types(source: DataSource, source_type: SourceType) -> None:
    assert replace(source, source_type=source_type).source_type is source_type


@pytest.mark.parametrize("venue_type", list(VenueType))
def test_all_documented_venue_types(venue: Venue, venue_type: VenueType) -> None:
    assert replace(venue, venue_type=venue_type).venue_type is venue_type
