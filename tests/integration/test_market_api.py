"""Actual PostgreSQL read composition through the HTTP boundary."""

from fastapi.testclient import TestClient
from sqlalchemy import Engine

from edgeeagle_api.local import market_transactions
from edgeeagle_api.main import create_app
from edgeeagle_persistence.markets import PostgresMarketAcceptanceRepository
from tests.integration.test_market_acceptance import candidates, seed_market_context
from tests.integration.test_repositories import repository_engine as repository_engine


def test_market_api_committed_visibility_and_pagination(repository_engine: Engine) -> None:
    batch = candidates()
    with repository_engine.begin() as conn:
        seed_market_context(conn)
    app = create_app(market_reads=market_transactions(repository_engine))
    with TestClient(app) as client:
        assert client.get("/v1/events/e1/markets").json() == {
            "items": [],
            "next_after_market_id": None,
        }
        with repository_engine.begin() as conn:
            PostgresMarketAcceptanceRepository(conn).accept(batch)
            assert client.get("/v1/events/e1/markets").json()["items"] == []
        markets = client.get("/v1/events/e1/markets")
        assert markets.status_code == 200
        market_id = markets.json()["items"][0]["market_id"]
        assert market_id == batch[0].market.market_id.value
        assert len(markets.json()["items"][0]["selections"]) == 3
        first = client.get(f"/v1/markets/{market_id}/quotes", params={"limit": 2})
        assert first.status_code == 200
        last = client.get(
            f"/v1/markets/{market_id}/quotes",
            params={
                "limit": 2,
                "after_quote_id": first.json()["next_after_quote_id"],
            },
        )
        assert last.status_code == 200 and last.json()["next_after_quote_id"] is None
        items = [*first.json()["items"], *last.json()["items"]]
        assert len(items) == 3
        assert {item["odds_decimal"] for item in items} == {"2.1", "3.2", "3.4"}
        assert all(item["provenance"]["raw"]["sha256"] == batch[0].raw.sha256 for item in items)
        assert all(item["available_at"] is None for item in items)
        assert client.get("/v1/events/missing/markets").status_code == 404
        assert client.get("/v1/markets/missing/quotes").status_code == 404
        with repository_engine.begin() as conn:
            assert PostgresMarketAcceptanceRepository(conn).accept(batch) == 0
        assert client.get(f"/v1/markets/{market_id}/quotes").json()["items"] == items
