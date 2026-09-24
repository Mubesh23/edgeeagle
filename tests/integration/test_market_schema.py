"""Market schema constraints on a disposable migrated PostgreSQL database."""

from decimal import Decimal
from unittest.mock import Mock

import pytest
from alembic import command
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError

from edgeeagle_ingestion.market_receipts import encode_market_receipt
from edgeeagle_ingestion.synthetic_markets import normalize_market_fixture
from edgeeagle_persistence.provenance import PostgresDataSourceRepository, PostgresVenueRepository
from edgeeagle_persistence.sports import PostgresSportsRepository
from tests.integration.test_event_acceptance import seed
from tests.integration.test_mapped_receipts import migration_config
from tests.integration.test_repositories import repository_engine as repository_engine
from tests.unit.test_event_normalization import fixture_payload
from tests.unit.test_market_normalization import context


def test_market_schema_constraints_and_roundtrip(repository_engine: Engine) -> None:
    raw, store, binding = fixture_payload(), Mock(), context()
    store.get.return_value = raw.body
    c = normalize_market_fixture(store, raw.reference(), (binding,))[0]
    with repository_engine.begin() as conn:
        seed(conn, include_source=False)
        PostgresDataSourceRepository(conn).add(binding.source)
        PostgresVenueRepository(conn).add(binding.venues[0].venue)
        PostgresSportsRepository(conn).add_event(binding.canonical_event, binding.entries)
        conn.execute(
            text("INSERT INTO markets VALUES (:id, :event, :type, :period)"),
            {
                "id": c.market.market_id.value,
                "event": c.market.event_id.value,
                "type": c.market.market_type.value,
                "period": c.market.period.value,
            },
        )
        for s in c.selections:
            conn.execute(
                text("INSERT INTO market_selections VALUES (:id, :market, :outcome, :p)"),
                {
                    "id": s.selection_id.value,
                    "market": s.market_id.value,
                    "outcome": s.outcome.value,
                    "p": s.participant_id.value if s.participant_id else None,
                },
            )
        receipt = {
            "id": "a" * 64,
            "market": c.market.market_id.value,
            "source": binding.source.data_source_id.value,
            "venue": binding.venues[0].venue.venue_id.value,
            "snapshot": encode_market_receipt(c).decode("ascii"),
        }
        conn.execute(
            text("INSERT INTO market_receipts VALUES (:id, :market, :source, :venue, :snapshot)"),
            receipt,
        )
        q = c.quotes[0]
        statement = text("""INSERT INTO market_quotes
            (quote_id, receipt_id, selection_id, market_id, data_source_id, venue_id,
             odds_decimal, ingested_at, observed_at, available_at)
            VALUES (:quote, :receipt, :selection, :market, :source, :venue,
                    :odds, :ingested, :observed, :available)""")
        values = {
            "quote": q.quote_id.value,
            "receipt": receipt["id"],
            "selection": q.selection_id.value,
            "market": receipt["market"],
            "source": receipt["source"],
            "venue": receipt["venue"],
            "odds": Decimal("2.12345678901234567890123456789"),
            "ingested": q.ingested_at,
            "observed": q.observed_at,
            "available": None,
        }
        for changes in (
            {"odds": Decimal("1")},
            {"odds": Decimal("NaN")},
            {"odds": Decimal("Infinity")},
            {"source": "missing"},
            {"venue": "missing"},
            {"market": "b" * 64},
            {"selection": "c" * 64},
            {"observed": "infinity"},
            {"available": "2099-01-01T00:00:00Z"},
        ):
            with pytest.raises(IntegrityError), conn.begin_nested():
                conn.execute(statement, values | changes)
        conn.execute(statement, values)
        assert conn.scalar(text("SELECT odds_decimal FROM market_quotes")) == values["odds"]
        assert conn.scalar(text("SELECT snapshot FROM market_receipts")) == receipt["snapshot"]
        with pytest.raises(IntegrityError), conn.begin_nested():
            conn.execute(statement, values)
        for table in ("markets", "market_selections", "market_receipts", "market_quotes"):
            for action in (f"DELETE FROM {table}", f"TRUNCATE {table} CASCADE"):
                with pytest.raises(IntegrityError, match="immutable"), conn.begin_nested():
                    conn.execute(text(action))
        with pytest.raises(IntegrityError, match="immutable"), conn.begin_nested():
            conn.execute(text("UPDATE market_quotes SET odds_decimal = 4"))
        config = migration_config(conn)
        command.downgrade(config, "0010_soccer_receipts")
        assert "markets" not in inspect(conn).get_table_names()
        assert conn.scalar(text("SELECT count(*) FROM events")) == 1
        command.upgrade(config, "head")
        assert conn.scalar(text("SELECT count(*) FROM market_quotes")) == 0
        assert conn.scalar(text("SELECT count(*) FROM events")) == 1
