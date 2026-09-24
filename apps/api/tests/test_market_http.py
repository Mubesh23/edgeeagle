"""Read-only HTTP boundary over authoritative market query results."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from decimal import Decimal
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError, TimeoutError

from edgeeagle_api.main import create_app
from edgeeagle_domain.market_query import (
    MarketPage,
    MarketReader,
    MarketView,
    QuoteObservation,
    QuotePage,
)
from tests.integration.test_market_acceptance import candidates


def test_market_api_serialization_and_query_forwarding() -> None:
    candidate = candidates()[0]
    price = "2.123456789012345678901234567890123456789"
    observation = QuoteObservation(
        quote=replace(candidate.quotes[0], odds_decimal=Decimal(price)),
        market_id=candidate.market.market_id,
        receipt_id="a" * 64,
        raw=candidate.raw,
        provider_event_id="fixture-event",
        provider_bookmaker_key="bovada",
        provider_market_key="h2h",
        provider_outcome_label="Draw",
        parser_version="synthetic-market-json-v1",
        normalizer_version="synthetic-market-bindings-v1",
        context_version="test-v1",
        usage="SYNTHETIC_ONLY",
    )
    reader = Mock(spec=MarketReader)
    reader.list_markets.return_value = MarketPage(
        (MarketView(candidate.market, candidate.selections),), candidate.market.market_id
    )
    reader.list_quotes.return_value = QuotePage((observation,), observation.quote.quote_id)

    @contextmanager
    def reads() -> Iterator[MarketReader]:
        yield reader

    with TestClient(create_app(market_reads=reads)) as client:
        response = client.get(
            "/v1/events/e1/markets", params={"limit": 1, "after_market_id": "cursor"}
        )
        assert response.status_code == 200
        item = response.json()["items"][0]
        assert item["market_type"] == "RESULT_3WAY"
        assert item["period"] == "REGULATION_TIME"
        assert len(item["selections"]) == 3
        assert response.json()["next_after_market_id"] == candidate.market.market_id.value
        identity, query = reader.list_markets.call_args.args
        assert (
            identity.value == "e1" and query.limit == 1 and query.after_market_id.value == "cursor"
        )
        result = client.get(
            "/v1/markets/market/quotes", params={"limit": 1, "after_quote_id": "cursor"}
        )
        assert result.status_code == 200
        body = result.json()
        assert body["next_after_quote_id"] == observation.quote.quote_id.value
        quote = body["items"][0]
        assert quote["odds_decimal"] == price
        assert quote["available_at"] is None
        assert quote["data_source_id"] == "synthetic-fixtures"
        assert quote["venue_id"] == "synthetic-book"
        assert quote["provenance"]["raw"]["sha256"] == candidate.raw.sha256
        assert quote["provenance"]["raw"]["capture"]["available_at"] is None
        assert quote["provenance"]["usage"] == "SYNTHETIC_ONLY"
        # Check forbidden object keys, not substrings of simulated_snapshot_at.
        assert '"bucket":' not in result.text and '"snapshot":' not in result.text
        assert quote["provenance"]["simulated_snapshot_at"] is None
        assert reader.list_quotes.call_args.args[1].after_quote_id.value == "cursor"
        reader.list_markets.return_value = None
        reader.list_quotes.return_value = None
        assert client.get("/v1/events/missing/markets").status_code == 404
        assert client.get("/v1/markets/missing/quotes").status_code == 404
        reader.list_markets.return_value = MarketPage((), None)
        reader.list_quotes.return_value = QuotePage((), None)
        assert client.get("/v1/events/e1/markets").json() == {
            "items": [],
            "next_after_market_id": None,
        }
        assert client.get("/v1/markets/market/quotes").json() == {
            "items": [],
            "next_after_quote_id": None,
        }


@pytest.mark.parametrize("path", ["/v1/events/e/markets", "/v1/markets/m/quotes"])
def test_market_api_unconfigured_and_read_only(path: str) -> None:
    with TestClient(create_app()) as client:
        assert client.get(path).status_code == 503
        for method in (client.post, client.put, client.patch, client.delete):
            assert method(path).status_code == 405


@pytest.mark.parametrize("path", ["/v1/events/e/markets", "/v1/markets/m/quotes"])
@pytest.mark.parametrize("query", ["limit=0", "limit=101", "limit=no", "limit=1.5"])
def test_market_api_invalid_limits(path: str, query: str) -> None:
    with TestClient(create_app()) as client:
        assert client.get(path + "?" + query).status_code == 422


@pytest.mark.parametrize(
    "path",
    [
        "/v1/events/%20/markets",
        "/v1/markets/%00/quotes",
        "/v1/events/e/markets?after_market_id=",
        "/v1/markets/m/quotes?after_quote_id=%00",
    ],
)
def test_market_api_invalid_ids(path: str) -> None:
    with TestClient(create_app()) as client:
        assert client.get(path).status_code == 422


@pytest.mark.parametrize(
    "error,status",
    [
        (OperationalError("secret-sql", {}, Exception("password")), 503),
        (TimeoutError("password"), 503),
        (RuntimeError("password"), 500),
    ],
)
def test_market_api_sanitizes_availability_but_not_programming_errors(
    error: Exception, status: int
) -> None:
    @contextmanager
    def reads() -> Iterator[MarketReader]:
        raise error
        yield  # pragma: no cover

    with TestClient(create_app(market_reads=reads), raise_server_exceptions=False) as client:
        for path in ("/v1/events/e/markets", "/v1/markets/m/quotes"):
            result = client.get(path)
            assert result.status_code == status
            assert "password" not in result.text and "secret-sql" not in result.text
