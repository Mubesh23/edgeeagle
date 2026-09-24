"""Bounded retained market/quote reads on disposable PostgreSQL."""

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock

import pytest
from sqlalchemy import Engine, text

from edgeeagle_domain.market_query import MarketQuery, MarketReader, QuoteQuery
from edgeeagle_domain.markets import MarketId, QuoteId
from edgeeagle_domain.sports import EventId
from edgeeagle_ingestion.market_acceptance import MarketAcceptanceConflict
from edgeeagle_ingestion.synthetic_markets import normalize_market_fixture
from edgeeagle_persistence.market_query import PostgresMarketReader
from edgeeagle_persistence.markets import PostgresMarketAcceptanceRepository
from tests.integration.test_market_acceptance import candidates, seed_market_context
from tests.integration.test_repositories import repository_engine as repository_engine
from tests.unit.test_event_normalization import fixture_payload
from tests.unit.test_market_normalization import context


def test_market_query_pages_provenance_and_absent_parents(repository_engine: Engine) -> None:
    batch = candidates()
    with repository_engine.begin() as conn:
        seed_market_context(conn)
    with repository_engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        with conn.begin():
            conn.execute(text("SET TRANSACTION READ ONLY"))
            reader: MarketReader = PostgresMarketReader(conn)
            empty = reader.list_markets(EventId("e1"), MarketQuery())
            assert empty is not None and empty.items == ()
            assert reader.list_markets(EventId("missing' OR TRUE --"), MarketQuery()) is None
            assert reader.list_quotes(MarketId("missing"), QuoteQuery()) is None
    with repository_engine.begin() as conn:
        PostgresMarketAcceptanceRepository(conn).accept(batch)
    with repository_engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        with conn.begin():
            conn.execute(text("SET TRANSACTION READ ONLY"))
            reader = PostgresMarketReader(conn)
            markets = reader.list_markets(EventId("e1"), MarketQuery(limit=1))
            assert markets is not None and len(markets.items) == 1
            assert markets.next_after_market_id is None
            assert markets.items[0].market == batch[0].market
            assert set(markets.items[0].selections) == set(batch[0].selections)
            after = reader.list_markets(
                EventId("e1"), MarketQuery(after_market_id=batch[0].market.market_id)
            )
            assert after is not None and after.items == ()
            first = reader.list_quotes(batch[0].market.market_id, QuoteQuery(limit=2))
            assert first is not None and len(first.items) == 2
            assert first.next_after_quote_id == first.items[-1].quote.quote_id
            last = reader.list_quotes(
                batch[0].market.market_id,
                QuoteQuery(limit=2, after_quote_id=first.next_after_quote_id),
            )
            assert last is not None and len(last.items) == 1 and last.next_after_quote_id is None
            observations = (*first.items, *last.items)
            assert tuple(o.quote for o in observations) == tuple(
                sorted(batch[0].quotes, key=lambda q: q.quote_id.value)
            )
            for value in observations:
                assert value.raw == batch[0].raw
                assert value.provider_event_id == batch[0].binding.event.key.provider_entity_id
                assert value.provider_bookmaker_key == "bovada"
                assert value.provider_market_key == "h2h"
                assert value.context_version == batch[0].binding.event.context_version
                assert value.parser_version == "synthetic-market-json-v1"
                assert value.normalizer_version == "synthetic-market-bindings-v1"
                assert value.usage == "SYNTHETIC_ONLY"
                assert value.quote.available_at is None
            end = reader.list_quotes(
                batch[0].market.market_id, QuoteQuery(after_quote_id=QuoteId("z' OR TRUE --"))
            )
            assert end is not None and end.items == ()


def test_market_query_snapshot_excludes_later_commits(repository_engine: Engine) -> None:
    batch = candidates()
    with repository_engine.begin() as conn:
        seed_market_context(conn)
        PostgresMarketAcceptanceRepository(conn).accept(batch)
    raw, store = fixture_payload(), Mock()
    raw = replace(
        raw, capture=replace(raw.capture, ingested_at=raw.capture.ingested_at + timedelta(days=1))
    )
    precise_price = "2.123456789012345678901234567890123456789"
    raw = replace(raw, body=raw.body.replace(b"2.1", precise_price.encode()))
    store.get.return_value = raw.body
    newer = normalize_market_fixture(store, raw.reference(), (context(),))
    with repository_engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        with conn.begin():
            conn.execute(text("SET TRANSACTION READ ONLY"))
            reader = PostgresMarketReader(conn)
            original = reader.list_quotes(batch[0].market.market_id, QuoteQuery())
            assert original is not None and len(original.items) == 3
            with repository_engine.begin() as writer:
                PostgresMarketAcceptanceRepository(writer).accept(newer)
            assert reader.list_quotes(batch[0].market.market_id, QuoteQuery()) == original
        with conn.begin():
            conn.execute(text("SET TRANSACTION READ ONLY"))
            updated = reader.list_quotes(batch[0].market.market_id, QuoteQuery())
            assert updated is not None and len(updated.items) == 6
            assert Decimal(precise_price) in {item.quote.odds_decimal for item in updated.items}


def test_market_query_retains_context_and_detects_quote_corruption(
    repository_engine: Engine,
) -> None:
    batch = candidates()
    with repository_engine.begin() as conn:
        seed_market_context(conn)
        PostgresMarketAcceptanceRepository(conn).accept(batch)
        conn.execute(
            text("UPDATE participants SET canonical_name = 'changed' WHERE participant_id = 'p1'")
        )
    with repository_engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        with conn.begin():
            conn.execute(text("SET TRANSACTION READ ONLY"))
            page = PostgresMarketReader(conn).list_quotes(batch[0].market.market_id, QuoteQuery())
            assert page is not None and len(page.items) == 3
            assert "Synthetic Home FC" in {item.provider_outcome_label for item in page.items}
    # Deliberate owner-level corruption only in this disposable test database.
    with repository_engine.begin() as conn:
        conn.execute(text("ALTER TABLE market_quotes DISABLE TRIGGER USER"))
        conn.execute(text("UPDATE market_quotes SET odds_decimal = 99"))
        conn.execute(text("ALTER TABLE market_quotes ENABLE TRIGGER USER"))
    with repository_engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        with conn.begin():
            conn.execute(text("SET TRANSACTION READ ONLY"))
            with pytest.raises(MarketAcceptanceConflict):
                PostgresMarketReader(conn).list_quotes(batch[0].market.market_id, QuoteQuery())


def test_market_query_requires_read_only_snapshot(repository_engine: Engine) -> None:
    with repository_engine.connect() as conn:
        reader = PostgresMarketReader(conn)
        with pytest.raises(RuntimeError):
            reader.list_markets(EventId("e1"), MarketQuery())
        with conn.begin(), pytest.raises(ValueError, match="REPEATABLE READ"):
            reader.list_markets(EventId("e1"), MarketQuery())
    with repository_engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        with conn.begin(), pytest.raises(ValueError, match="READ ONLY"):
            PostgresMarketReader(conn).list_quotes(MarketId("missing"), QuoteQuery())
