"""Bounded market read contracts have no persistence dependencies."""

import pytest

from edgeeagle_domain.market_query import MarketQuery, QuoteQuery
from edgeeagle_domain.markets import MarketId, QuoteId


@pytest.mark.parametrize("limit", [0, 101, True, 1.5, "1"])
def test_market_query_rejects_invalid_limits(limit: object) -> None:
    with pytest.raises(ValueError):
        MarketQuery(limit=limit)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        QuoteQuery(limit=limit)  # type: ignore[arg-type]


def test_market_query_defaults_and_typed_cursors() -> None:
    assert MarketQuery().limit == QuoteQuery().limit == 50
    assert MarketQuery(limit=1, after_market_id=MarketId("a")).after_market_id == MarketId("a")
    assert QuoteQuery(limit=100, after_quote_id=QuoteId("z")).after_quote_id == QuoteId("z")
    with pytest.raises(TypeError):
        MarketQuery(after_market_id=QuoteId("wrong"))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        QuoteQuery(after_quote_id=MarketId("wrong"))  # type: ignore[arg-type]
