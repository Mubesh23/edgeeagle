"""Atomic quote acceptance, exact retry and retained readback on real PostgreSQL."""

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from threading import Barrier
from unittest.mock import Mock

import pytest
from sqlalchemy import Connection, Engine, text

from edgeeagle_domain.provenance import VenueId
from edgeeagle_ingestion.market_acceptance import MarketAcceptanceConflict, receipt_id
from edgeeagle_ingestion.synthetic_markets import MarketCandidate, normalize_market_fixture
from edgeeagle_persistence.markets import PostgresMarketAcceptanceRepository
from edgeeagle_persistence.provenance import PostgresDataSourceRepository, PostgresVenueRepository
from edgeeagle_persistence.sports import PostgresSportsRepository
from tests.integration.test_event_acceptance import seed
from tests.integration.test_repositories import repository_engine as repository_engine
from tests.unit.test_event_normalization import fixture_payload
from tests.unit.test_market_normalization import context


def candidates() -> tuple[MarketCandidate, ...]:
    raw, store = fixture_payload(), Mock()
    store.get.return_value = raw.body
    return normalize_market_fixture(store, raw.reference(), (context(),))


def seed_market_context(conn: Connection) -> None:
    b = context()
    seed(conn, include_source=False)
    PostgresDataSourceRepository(conn).add(b.source)
    PostgresVenueRepository(conn).add(b.venues[0].venue)
    PostgresSportsRepository(conn).add_event(b.canonical_event, b.entries)


def test_market_acceptance_commit_retry_and_new_capture(repository_engine: Engine) -> None:
    batch = candidates()
    with repository_engine.begin() as conn:
        seed_market_context(conn)
        repo = PostgresMarketAcceptanceRepository(conn)
        assert repo.accept(batch) == 1
        assert repo.accept(batch) == 0
        assert repo.get(receipt_id(batch[0])) == batch[0]
        with repository_engine.begin() as reader:
            assert PostgresMarketAcceptanceRepository(reader).get(receipt_id(batch[0])) is None
    raw, store = fixture_payload(), Mock()
    raw = replace(
        raw, capture=replace(raw.capture, ingested_at=raw.capture.ingested_at + timedelta(days=1))
    )
    store.get.return_value = raw.body
    newer = normalize_market_fixture(store, raw.reference(), (context(),))
    with repository_engine.begin() as conn:
        repo = PostgresMarketAcceptanceRepository(conn)
        assert repo.get(receipt_id(batch[0])) == batch[0]
        assert repo.accept(newer) == 1
        assert conn.scalar(text("SELECT count(*) FROM markets")) == 1
        assert conn.scalar(text("SELECT count(*) FROM market_selections")) == 3
        assert conn.scalar(text("SELECT count(*) FROM market_quotes")) == 6
        assert repo.get(receipt_id(batch[0])) == batch[0]


def test_market_acceptance_conflict_and_rollback(repository_engine: Engine) -> None:
    batch = candidates()
    with repository_engine.begin() as conn:
        seed_market_context(conn)
    with pytest.raises(RuntimeError), repository_engine.begin() as conn:
        assert PostgresMarketAcceptanceRepository(conn).accept(batch) == 1
        raise RuntimeError("outer rollback")
    with repository_engine.begin() as conn:
        assert conn.scalar(text("SELECT count(*) FROM markets")) == 0
        repo = PostgresMarketAcceptanceRepository(conn)
        assert repo.accept(batch) == 1
        changed = replace(
            batch[0],
            quotes=(replace(batch[0].quotes[0], odds_decimal=Decimal("9")), *batch[0].quotes[1:]),
        )
        with pytest.raises(MarketAcceptanceConflict):
            repo.accept((changed,))
        assert repo.get(receipt_id(batch[0])) == batch[0]
        assert conn.scalar(text("SELECT count(*) FROM market_quotes")) == 3


def test_market_acceptance_missing_reference_is_atomic(repository_engine: Engine) -> None:
    with repository_engine.begin() as conn:
        repo = PostgresMarketAcceptanceRepository(conn)
        with pytest.raises(MarketAcceptanceConflict):
            repo.accept(candidates())
        assert conn.scalar(text("SELECT count(*) FROM markets")) == 0


def test_market_acceptance_late_sql_failure_rolls_back_entire_operation(
    repository_engine: Engine,
) -> None:
    with repository_engine.begin() as conn:
        seed_market_context(conn)
        conn.execute(
            text("""CREATE FUNCTION test_reject_quote() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
            IF (SELECT count(*) FROM market_quotes) = 2 THEN
                RAISE EXCEPTION 'injected final quote failure' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
            END; $$""")
        )
        conn.execute(
            text("""CREATE TRIGGER test_reject_quote BEFORE INSERT ON market_quotes
            FOR EACH ROW EXECUTE FUNCTION test_reject_quote()""")
        )
        with pytest.raises(MarketAcceptanceConflict):
            PostgresMarketAcceptanceRepository(conn).accept(candidates())
        for table in ("markets", "market_selections", "market_receipts", "market_quotes"):
            assert conn.scalar(text(f"SELECT count(*) FROM {table}")) == 0
        assert conn.scalar(text("SELECT count(*) FROM events")) == 1


def test_market_acceptance_reference_drift_does_not_rewrite_receipt(
    repository_engine: Engine,
) -> None:
    batch = candidates()
    with repository_engine.begin() as conn:
        seed_market_context(conn)
        repo = PostgresMarketAcceptanceRepository(conn)
        assert repo.accept(batch) == 1
        conn.execute(
            text("UPDATE participants SET canonical_name = 'changed' WHERE participant_id = 'p1'")
        )
        assert repo.get(receipt_id(batch[0])) == batch[0]
        with pytest.raises(MarketAcceptanceConflict):
            repo.accept(batch)


def test_market_acceptance_multiple_bookmakers_roll_back_together(
    repository_engine: Engine,
) -> None:
    raw, store, binding = fixture_payload(), Mock(), context()
    second = replace(
        binding.venues[0],
        provider_key="second-book",
        venue=replace(binding.venues[0].venue, venue_id=VenueId("second-venue")),
    )
    binding = replace(binding, venues=(*binding.venues, second))
    payload = json.loads(raw.body)
    payload[0]["bookmakers"].append({**payload[0]["bookmakers"][0], "key": "second-book"})
    raw = replace(raw, body=json.dumps(payload).encode())
    store.get.return_value = raw.body
    batch = normalize_market_fixture(store, raw.reference(), (binding,))
    with repository_engine.begin() as conn:
        seed_market_context(conn)
        PostgresVenueRepository(conn).add(second.venue)
        conn.execute(
            text("""CREATE FUNCTION test_reject_second_receipt() RETURNS trigger
            LANGUAGE plpgsql AS $$ BEGIN
            IF (SELECT count(*) FROM market_quotes) = 5 THEN
                RAISE EXCEPTION 'injected second receipt failure' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
            END; $$""")
        )
        conn.execute(
            text("""CREATE TRIGGER test_reject_second_receipt BEFORE INSERT ON market_quotes
            FOR EACH ROW EXECUTE FUNCTION test_reject_second_receipt()""")
        )
        repo = PostgresMarketAcceptanceRepository(conn)
        with pytest.raises(MarketAcceptanceConflict):
            repo.accept(batch)
        for table in ("markets", "market_selections", "market_receipts", "market_quotes"):
            assert conn.scalar(text(f"SELECT count(*) FROM {table}")) == 0
        conn.execute(text("DROP TRIGGER test_reject_second_receipt ON market_quotes"))
        assert repo.accept(tuple(reversed(batch))) == 2
        assert repo.accept(batch) == 0
        assert conn.scalar(text("SELECT count(*) FROM market_quotes")) == 6


def test_market_acceptance_requires_transaction_and_read_committed(
    repository_engine: Engine,
) -> None:
    with repository_engine.connect() as conn:
        with pytest.raises(RuntimeError):
            PostgresMarketAcceptanceRepository(conn).accept(candidates())
    with repository_engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        with conn.begin(), pytest.raises(ValueError, match="READ COMMITTED"):
            PostgresMarketAcceptanceRepository(conn).accept(candidates())


@pytest.mark.parametrize("conflicting", [False, True])
def test_market_acceptance_concurrent_writers(repository_engine: Engine, conflicting: bool) -> None:
    batch, barrier = candidates(), Barrier(2)
    changed = replace(
        batch[0],
        quotes=(replace(batch[0].quotes[0], odds_decimal=Decimal("8")), *batch[0].quotes[1:]),
    )
    with repository_engine.begin() as conn:
        seed_market_context(conn)

    def run(value: tuple[MarketCandidate, ...]) -> int:
        with repository_engine.begin() as conn:
            conn.execute(text("SET LOCAL lock_timeout = '5s'"))
            barrier.wait(timeout=5)
            try:
                return PostgresMarketAcceptanceRepository(conn).accept(value)
            except MarketAcceptanceConflict:
                return -1

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(run, batch), pool.submit(run, (changed,) if conflicting else batch)]
        assert sorted(job.result(timeout=10) for job in jobs) == (
            [-1, 1] if conflicting else [0, 1]
        )
    with repository_engine.begin() as conn:
        assert conn.scalar(text("SELECT count(*) FROM market_quotes")) == 3
