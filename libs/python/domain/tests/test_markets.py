"""Canonical 1X2 semantics and observed prices, with no provider or IO dependencies."""

import hashlib
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal, localcontext

import pytest

from edgeeagle_domain.markets import (
    Market,
    MarketId,
    MarketPeriod,
    MarketType,
    Outcome,
    Quote,
    QuoteId,
    Selection,
    SelectionId,
    validate_market_selections,
)
from edgeeagle_domain.provenance import DataSourceId, VenueId
from edgeeagle_domain.sports import EventId, EventParticipant, ParticipantId


def market() -> Market:
    return Market(
        event_id=EventId("event-1"),
        market_type=MarketType.RESULT_3WAY,
        period=MarketPeriod.REGULATION_TIME,
    )


def selections() -> tuple[Selection, ...]:
    return tuple(
        Selection(market_id=market().market_id, outcome=outcome, participant_id=participant)
        for outcome, participant in (
            (Outcome.HOME, ParticipantId("home")),
            (Outcome.DRAW, None),
            (Outcome.AWAY, ParticipantId("away")),
        )
    )


def entries() -> tuple[EventParticipant, ...]:
    return tuple(
        EventParticipant(event_id=EventId("event-1"), participant_id=ParticipantId(p), role=r)
        for p, r in (("home", "HOME"), ("away", "AWAY"))
    )


def quote() -> Quote:
    return Quote(
        quote_id=QuoteId("observation-1"),
        selection_id=selections()[0].selection_id,
        data_source_id=DataSourceId("synthetic-aggregator"),
        venue_id=VenueId("synthetic-book"),
        odds_decimal=Decimal("2.100000000000000000000000000001"),
        ingested_at=datetime(2026, 9, 23, tzinfo=UTC),
    )


def test_identity_golden_preimages_and_semantics() -> None:
    preimage = (
        b'{"event_id":"event-1","identity_version":1,"market_type":"RESULT_3WAY",'
        b'"period":"REGULATION_TIME"}'
    )
    expected = hashlib.sha256(preimage).hexdigest()
    assert market().market_id == MarketId(expected)
    for selection in selections():
        wire = (
            '{"identity_version":1,"market_id":"'
            + expected
            + '","outcome":"'
            + selection.outcome.value
            + '"}'
        ).encode("ascii")
        assert selection.selection_id == SelectionId(hashlib.sha256(wire).hexdigest())
    assert len({s.selection_id for s in selections()}) == 3
    assert replace(market(), event_id=EventId("event-2")).market_id != market().market_id
    # Reference edits do not silently allocate a different semantic identity.
    assert replace(selections()[0], participant_id=ParticipantId("other")).selection_id == (
        selections()[0].selection_id
    )


def test_complete_selections_and_context_are_order_independent() -> None:
    validate_market_selections(market(), selections(), entries())
    validate_market_selections(market(), tuple(reversed(selections())), tuple(reversed(entries())))


@pytest.mark.parametrize("bad", [(), selections()[:2], (selections()[0],) * 3])
def test_incomplete_or_duplicate_selections_fail(bad: tuple[Selection, ...]) -> None:
    with pytest.raises(ValueError):
        validate_market_selections(market(), bad, entries())


def test_cross_market_and_participant_mismatches_fail() -> None:
    for replacement in (
        replace(selections()[0], market_id=MarketId("different")),
        replace(selections()[0], participant_id=ParticipantId("away")),
    ):
        with pytest.raises(ValueError):
            validate_market_selections(market(), (replacement, *selections()[1:]), entries())
    for bad in (
        entries()[:1],
        entries() * 2,
        (replace(entries()[0], role="AWAY"), entries()[1]),
        (replace(entries()[0], event_id=EventId("other")), entries()[1]),
    ):
        with pytest.raises(ValueError):
            validate_market_selections(market(), selections(), bad)


def test_draw_and_team_participant_rules() -> None:
    with pytest.raises(ValueError):
        replace(selections()[1], participant_id=ParticipantId("home"))
    with pytest.raises(ValueError):
        replace(selections()[0], participant_id=None)


@pytest.mark.parametrize(
    "value",
    [
        Decimal("1"),
        Decimal("0"),
        Decimal("-2"),
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
    ],
)
def test_invalid_prices(value: Decimal) -> None:
    with pytest.raises(ValueError):
        replace(quote(), odds_decimal=value)


@pytest.mark.parametrize("value", [2.1, 2, True, "2.1", None])
def test_no_implicit_price_coercion(value: object) -> None:
    with pytest.raises(TypeError):
        replace(quote(), odds_decimal=value)  # type: ignore[arg-type]


def test_quote_preserves_exact_price_source_and_unknown_times() -> None:
    with localcontext() as ctx:
        ctx.prec = 3
        q = quote()
        assert str(q.odds_decimal) == "2.100000000000000000000000000001"
    assert q.data_source_id.value == "synthetic-aggregator"
    assert q.venue_id.value == "synthetic-book"
    assert q.available_at is q.observed_at is q.effective_at is None
    assert q.provider_quote_id is None
    assert replace(q, venue_id=VenueId("other")).data_source_id == q.data_source_id
    with pytest.raises(FrozenInstanceError):
        q.odds_decimal = Decimal("3")  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        market().event_id = EventId("other")  # type: ignore[misc]


@pytest.mark.parametrize("field", ["effective_at", "observed_at", "available_at", "ingested_at"])
def test_times_are_aware_and_normalized_to_utc(field: str) -> None:
    with pytest.raises(ValueError):
        replace(quote(), **{field: datetime(2026, 1, 1)})  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        replace(quote(), **{field: "2026-01-01"})  # type: ignore[arg-type]
    t = datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=2)))
    assert getattr(replace(quote(), **{field: t}), field) == t.astimezone(UTC)  # type: ignore[arg-type]


def test_availability_order_and_type_safety() -> None:
    q = quote()
    assert replace(q, available_at=q.ingested_at).available_at == q.ingested_at
    with pytest.raises(ValueError):
        replace(q, available_at=q.ingested_at + timedelta(microseconds=1))
    with pytest.raises(TypeError):
        replace(q, ingested_at=None)  # type: ignore[arg-type]
    for field, value in (
        ("data_source_id", q.venue_id),
        ("venue_id", q.data_source_id),
        ("quote_id", "raw"),
        ("selection_id", MarketId("market")),
    ):
        with pytest.raises(TypeError):
            replace(q, **{field: value})  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        replace(q, provider_quote_id=" ")
    assert replace(q, provider_quote_id="native-1").provider_quote_id == "native-1"


def test_unsupported_semantics_and_mutable_collections_fail() -> None:
    for field, value in (
        ("market_type", "RESULT_3WAY"),
        ("period", "EXTRA_TIME"),
        ("event_id", "event-1"),
    ):
        with pytest.raises(TypeError):
            replace(market(), **{field: value})  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        replace(selections()[0], outcome="HOME")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        validate_market_selections(market(), list(selections()), entries())  # type: ignore[arg-type]


@pytest.mark.parametrize("kind", [MarketId, SelectionId, QuoteId])
def test_typed_ids_reject_blank_and_nontext(kind: type[MarketId | SelectionId | QuoteId]) -> None:
    for value in ("", " padded "):
        with pytest.raises(ValueError):
            kind(value)
    with pytest.raises(TypeError):
        kind(123)  # type: ignore[arg-type]
