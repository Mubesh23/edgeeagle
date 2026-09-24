from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal

import pytest
from sqlalchemy import Engine, text

from edgeeagle_domain.raw import RawPayload
from edgeeagle_ingestion.market_acceptance import MarketAcceptanceConflict
from edgeeagle_persistence.mappings import PostgresMappingRepository
from edgeeagle_persistence.odds_captures import (
    PostgresOddsCaptureRepository,
    capture_identity,
)
from tests.integration.test_odds_capture_reads import seed_odds_context
from tests.integration.test_repositories import repository_engine as repository_engine
from tests.unit.test_odds_receipts import receipt


def test_odds_acceptance_atomic_idempotent_and_conflicting(repository_engine: Engine) -> None:
    capture, _, _ = receipt()
    with repository_engine.begin() as conn:
        seed_odds_context(conn, capture)
        for revision in capture.evidence[0].references.revisions:
            PostgresMappingRepository(conn).append(revision)
        repo = PostgresOddsCaptureRepository(conn)
        assert repo.accept(capture) == 1
        assert repo.accept(capture) == 0
        assert repo.get(capture_identity(capture)) == capture
        observation = capture.observations[0]
        changed = replace(
            capture,
            observations=(
                replace(
                    observation,
                    quotes=(
                        replace(observation.quotes[0], odds_decimal=Decimal("2.5")),
                        *observation.quotes[1:],
                    ),
                ),
            ),
        )
        with pytest.raises(MarketAcceptanceConflict):
            repo.accept(changed)
        assert repo.get(capture_identity(capture)) == capture
        assert conn.scalar(text("SELECT count(*) FROM odds_capture_quotes")) == 3
        assert conn.scalar(text("SELECT count(*) FROM market_quotes")) == 0


@pytest.mark.parametrize("empty", [False, True])
def test_odds_acceptance_first_writer_race(repository_engine: Engine, empty: bool) -> None:
    capture, _, _ = receipt()
    with repository_engine.begin() as conn:
        seed_odds_context(conn, capture)
        for revision in capture.evidence[0].references.revisions:
            PostgresMappingRepository(conn).append(revision)
    if empty:
        raw = RawPayload(capture=capture.manifest.raw.capture, body=b"[]")
        capture = replace(
            capture,
            manifest=replace(capture.manifest, raw=raw.reference()),
            evidence=(),
            observations=(),
        )

    def accept() -> int:
        with repository_engine.begin() as conn:
            conn.execute(text("SET LOCAL lock_timeout = '5s'"))
            return PostgresOddsCaptureRepository(conn).accept(capture)

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(lambda _: accept(), range(2))) == [0, 1]
    with repository_engine.begin() as conn:
        assert PostgresOddsCaptureRepository(conn).get(capture_identity(capture)) == capture
        assert conn.scalar(text("SELECT count(*) FROM odds_capture_quotes")) == (0 if empty else 3)


def test_odds_acceptance_outer_rollback(repository_engine: Engine) -> None:
    capture, _, _ = receipt()
    with repository_engine.begin() as conn:
        seed_odds_context(conn, capture)
        for revision in capture.evidence[0].references.revisions:
            PostgresMappingRepository(conn).append(revision)
    with repository_engine.connect() as conn:
        tx = conn.begin()
        assert PostgresOddsCaptureRepository(conn).accept(capture) == 1
        tx.rollback()
    with repository_engine.begin() as conn:
        assert PostgresOddsCaptureRepository(conn).get(capture_identity(capture)) is None


def test_odds_acceptance_late_failure_rolls_back_whole_capture(repository_engine: Engine) -> None:
    capture, _, _ = receipt()
    with repository_engine.begin() as conn:
        seed_odds_context(conn, capture)
        for revision in capture.evidence[0].references.revisions:
            PostgresMappingRepository(conn).append(revision)
        # Disposable test-only constraint fails after earlier inserts succeed.
        conn.execute(
            text("ALTER TABLE odds_capture_quotes ADD CONSTRAINT test_reject CHECK (false)")
        )
        with pytest.raises(MarketAcceptanceConflict):
            PostgresOddsCaptureRepository(conn).accept(capture)
        for table in (
            "markets",
            "market_selections",
            "odds_capture_receipts",
            "odds_capture_quotes",
        ):
            assert conn.scalar(text(f"SELECT count(*) FROM {table}")) == 0


def test_odds_acceptance_missing_mapping_fails_without_writes(repository_engine: Engine) -> None:
    capture, _, _ = receipt()
    with repository_engine.begin() as conn:
        seed_odds_context(conn, capture)
        with pytest.raises(MarketAcceptanceConflict):
            PostgresOddsCaptureRepository(conn).accept(capture)
        assert conn.scalar(text("SELECT count(*) FROM odds_capture_receipts")) == 0


def test_odds_acceptance_requires_caller_transaction(repository_engine: Engine) -> None:
    capture, _, _ = receipt()
    with repository_engine.connect() as conn:
        with pytest.raises(RuntimeError, match="caller-owned"):
            PostgresOddsCaptureRepository(conn).accept(capture)
    with repository_engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        with conn.begin(), pytest.raises(ValueError, match="READ COMMITTED"):
            PostgresOddsCaptureRepository(conn).accept(capture)
