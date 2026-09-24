"""Authored local file -> Floci raw -> atomic PostgreSQL -> read-only HTTP."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient
from mypy_boto3_s3 import S3Client
from sqlalchemy import Engine, text

from edgeeagle_api.local import market_transactions
from edgeeagle_api.main import create_app
from edgeeagle_domain.raw import RawPayloadIntegrityError
from edgeeagle_ingestion.market_acceptance import MarketAcceptanceRepository
from edgeeagle_ingestion.market_import import MarketAcceptanceTransactions, import_market_fixture
from edgeeagle_ingestion.offline import LocalFileImporter
from edgeeagle_ingestion.synthetic_markets import MAX_BYTES, replay_market_fixture
from edgeeagle_persistence.markets import PostgresMarketAcceptanceRepository
from edgeeagle_persistence.raw import S3RawPayloadStore
from tests.integration.test_market_acceptance import seed_market_context
from tests.integration.test_raw_storage import raw_bucket as raw_bucket
from tests.integration.test_repositories import repository_engine as repository_engine
from tests.unit.test_event_normalization import fixture_payload
from tests.unit.test_market_normalization import context

FIXTURE = Path(__file__).parents[1] / "fixtures/providers/the_odds_api/odds-success.json"


def acceptance_transactions(engine: Engine) -> MarketAcceptanceTransactions:
    @contextmanager
    def transactions() -> Iterator[MarketAcceptanceRepository]:
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text("SET LOCAL statement_timeout = '10s'"))
            yield PostgresMarketAcceptanceRepository(connection)

    return transactions


@pytest.mark.parametrize("loss", ["missing", "body", "metadata"])
def test_market_fixture_raw_to_api(
    repository_engine: Engine,
    raw_bucket: tuple[S3Client, str],
    loss: str,
) -> None:
    s3, bucket = raw_bucket
    raw = fixture_payload()
    store = S3RawPayloadStore(s3, bucket)
    importer = LocalFileImporter(FIXTURE, raw.capture, max_bytes=MAX_BYTES)
    transactions = acceptance_transactions(repository_engine)
    with repository_engine.begin() as connection:
        seed_market_context(connection)

    def run() -> int:
        return import_market_fixture(importer, store, (context(),), transactions).inserted_receipts

    result = import_market_fixture(importer, store, (context(),), transactions)
    assert result.inserted_receipts == 1 and result.raw == raw.reference()
    assert run() == 0
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda _: run(), range(2))) == [0, 0]
    assert store.get(result.raw) == FIXTURE.read_bytes()
    with repository_engine.begin() as connection:
        repository = PostgresMarketAcceptanceRepository(connection)
        candidate = repository.get(result.receipt_ids[0])
        assert candidate is not None
        assert connection.scalar(text("SELECT count(*) FROM markets")) == 1
        assert connection.scalar(text("SELECT count(*) FROM market_selections")) == 3
        assert connection.scalar(text("SELECT count(*) FROM market_receipts")) == 1
        assert connection.scalar(text("SELECT count(*) FROM market_quotes")) == 3
        assert connection.scalar(text("SELECT count(*) FROM event_outbox")) == 0
        connection.execute(
            text("UPDATE participants SET canonical_name = 'changed' WHERE participant_id = 'p1'")
        )
    replay_market_fixture(store, (candidate,))
    app = create_app(market_reads=market_transactions(repository_engine))
    with TestClient(app) as client:
        markets = client.get("/v1/events/e1/markets")
        assert markets.status_code == 200 and len(markets.json()["items"]) == 1
        market_id = markets.json()["items"][0]["market_id"]
        response = client.get(f"/v1/markets/{market_id}/quotes")
        assert response.status_code == 200
        items = response.json()["items"]
        assert {item["odds_decimal"] for item in items} == {"2.1", "3.2", "3.4"}
        for item in items:
            assert item["data_source_id"] == "synthetic-fixtures"
            assert item["venue_id"] == "synthetic-book"
            assert item["available_at"] is None
            assert item["provenance"]["usage"] == "SYNTHETIC_ONLY"
            assert item["provenance"]["raw"]["sha256"] == raw.reference().sha256
            assert item["provenance"]["receipt_id"] == result.receipt_ids[0]
            assert item["provenance"]["context_version"] == context().event.context_version
        objects = s3.list_objects_v2(Bucket=bucket)["Contents"]
        assert len(objects) == 1
        key = objects[0]["Key"]
        if loss == "missing":
            s3.delete_object(Bucket=bucket, Key=key)
        else:
            metadata = s3.head_object(Bucket=bucket, Key=key)["Metadata"]
            s3.put_object(
                Bucket=bucket,
                Key=key,
                Body=b"corrupt" if loss == "body" else raw.body,
                Metadata={} if loss == "metadata" else metadata,
            )
        with pytest.raises((FileNotFoundError, RawPayloadIntegrityError)):
            replay_market_fixture(store, (candidate,))
        # Observation reads do not claim fresh raw verification and need no S3.
        assert client.get(f"/v1/markets/{market_id}/quotes").json() == response.json()


def test_market_import_bad_final_outcome_retains_raw_without_writes(
    repository_engine: Engine,
    raw_bucket: tuple[S3Client, str],
    tmp_path: Path,
) -> None:
    s3, bucket = raw_bucket
    raw = fixture_payload()
    raw = replace(raw, body=raw.body.replace(b'"price": 3.2', b'"price": 1'))
    path = tmp_path / "invalid-market.json"
    path.write_bytes(raw.body)
    store, transactions = S3RawPayloadStore(s3, bucket), Mock()
    with pytest.raises(ValueError):
        import_market_fixture(
            LocalFileImporter(path, raw.capture, max_bytes=MAX_BYTES),
            store,
            (context(),),
            transactions,
        )
    transactions.assert_not_called()
    assert store.get(raw.reference()) == raw.body
    with repository_engine.begin() as connection:
        for table in ("markets", "market_selections", "market_receipts", "market_quotes"):
            assert connection.scalar(text(f"SELECT count(*) FROM {table}")) == 0
