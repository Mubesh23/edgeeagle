"""Authored v4 fixture through real local retention, references, acceptance and API."""

import json
from collections.abc import Iterator
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
from edgeeagle_domain.mappings import MappingStatus
from edgeeagle_domain.raw import RawPayload, RawPayloadIntegrityError
from edgeeagle_ingestion.market_acceptance import MarketAcceptanceConflict
from edgeeagle_ingestion.odds_acceptance import OddsCaptureRepository
from edgeeagle_ingestion.odds_import import (
    OddsCaptureTransactions,
    accept_retained_odds_capture,
    import_odds_capture,
)
from edgeeagle_ingestion.odds_normalization import replay_odds_capture
from edgeeagle_ingestion.offline import LocalFileImporter
from edgeeagle_persistence.mappings import PostgresMappingRepository
from edgeeagle_persistence.odds_captures import PostgresOddsCaptureRepository
from edgeeagle_persistence.odds_references import odds_reference_reads
from edgeeagle_persistence.raw import S3RawPayloadStore
from tests.integration.test_odds_capture_reads import seed_odds_context
from tests.integration.test_raw_storage import raw_bucket as raw_bucket
from tests.integration.test_repositories import repository_engine as repository_engine
from tests.unit.test_odds_manifest import NOW
from tests.unit.test_odds_normalization import inputs
from tests.unit.test_odds_receipts import receipt

FIXTURE = Path("tests/fixtures/providers/the_odds_api/pre-match-v1/odds-success.json")


def acceptance_transactions(engine: Engine) -> OddsCaptureTransactions:
    @contextmanager
    def transactions() -> Iterator[OddsCaptureRepository]:
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL lock_timeout = '5s'"))
            conn.execute(text("SET LOCAL statement_timeout = '10s'"))
            yield PostgresOddsCaptureRepository(conn)

    return transactions


@pytest.mark.parametrize("mapping_change", ["corrected", "revoked"])
def test_odds_fixture_raw_to_api_retained_replay(
    repository_engine: Engine,
    raw_bucket: tuple[S3Client, str],
    mapping_change: str,
) -> None:
    manifest, guard, refs, _, _, _ = inputs()
    expected, _, _ = receipt()
    s3, bucket = raw_bucket
    store = S3RawPayloadStore(s3, bucket)
    importer = LocalFileImporter(FIXTURE, manifest.raw.capture, max_bytes=1024 * 1024)
    reads, writes = (
        odds_reference_reads(repository_engine),
        acceptance_transactions(repository_engine),
    )
    with repository_engine.begin() as conn:
        seed_odds_context(conn, expected)
        for revision in refs.revisions:
            PostgresMappingRepository(conn).append(revision)

    result = import_odds_capture(importer, store, manifest, (guard,), reads, writes, as_of=NOW)
    assert result.inserted_receipts == 1
    assert (
        import_odds_capture(
            importer, store, manifest, (guard,), reads, writes, as_of=NOW
        ).inserted_receipts
        == 0
    )
    with repository_engine.begin() as conn:
        retained = PostgresOddsCaptureRepository(conn).get(result.capture_id)
        assert retained == expected
        assert conn.scalar(text("SELECT count(*) FROM odds_capture_receipts")) == 1
        assert conn.scalar(text("SELECT count(*) FROM odds_capture_quotes")) == 3
        assert conn.scalar(text("SELECT count(*) FROM market_quotes")) == 0
        assert conn.scalar(text("SELECT count(*) FROM event_outbox")) == 0
    assert retained is not None
    market_id = retained.observations[0].market.market_id.value
    with TestClient(create_app(market_reads=market_transactions(repository_engine))) as client:
        before = client.get(f"/v1/markets/{market_id}/quotes")
        assert before.status_code == 200
        assert {q["odds_decimal"] for q in before.json()["items"]} == {
            "2.12345678901234567890123456789",
            "3.2",
            "3.4",
        }
        for quote in before.json()["items"]:
            assert quote["available_at"] is None
            assert quote["data_source_id"] != quote["venue_id"]
            assert quote["provenance"]["receipt_id"] == result.capture_id
            assert quote["provenance"]["usage"] == "SYNTHETIC_ONLY"
        with repository_engine.begin() as conn:
            PostgresMappingRepository(conn).append(
                replace(
                    refs.revisions[1],
                    revision=2,
                    validated_by="authored-second-review",
                    status=MappingStatus.REVOKED
                    if mapping_change == "revoked"
                    else MappingStatus.MAPPED,
                )
            )
        # Fresh normalization must not silently replace original receipt evidence.
        with pytest.raises((ValueError, MarketAcceptanceConflict)):
            import_odds_capture(importer, store, manifest, (guard,), reads, writes, as_of=NOW)
        replay_odds_capture(store, retained)
        assert accept_retained_odds_capture(store, retained, writes).inserted_receipts == 0
        assert client.get(f"/v1/markets/{market_id}/quotes").json() == before.json()
        assert len(s3.list_objects_v2(Bucket=bucket)["Contents"]) == 1
        # Tamper only with this disposable test bucket; fail before any write transaction.
        key = s3.list_objects_v2(Bucket=bucket)["Contents"][0]["Key"]
        s3.put_object(Bucket=bucket, Key=key, Body=b"corrupt")
        forbidden_writes = Mock()
        with pytest.raises(RawPayloadIntegrityError):
            accept_retained_odds_capture(store, retained, forbidden_writes)
        forbidden_writes.assert_not_called()
        assert client.get(f"/v1/markets/{market_id}/quotes").json() == before.json()


@pytest.mark.parametrize("shape", ["empty", "no_quotes", "invalid"])
def test_odds_import_empty_and_invalid_capture(
    repository_engine: Engine,
    raw_bucket: tuple[S3Client, str],
    tmp_path: Path,
    shape: str,
) -> None:
    manifest, guard, refs, _, _, _ = inputs()
    expected, _, _ = receipt()
    doc = json.loads(FIXTURE.read_bytes())
    if shape == "empty":
        doc = []
    elif shape == "no_quotes":
        doc[0]["bookmakers"][0]["markets"] = []
    else:
        doc[0]["bookmakers"][0]["markets"][0]["outcomes"][-1]["price"] = 1
    raw = RawPayload(capture=manifest.raw.capture, body=json.dumps(doc).encode())
    manifest = replace(manifest, raw=raw.reference())
    path = tmp_path / "authored.json"
    path.write_bytes(raw.body)
    s3, bucket = raw_bucket
    store = S3RawPayloadStore(s3, bucket)
    with repository_engine.begin() as conn:
        seed_odds_context(conn, expected)
        for revision in refs.revisions:
            PostgresMappingRepository(conn).append(revision)
    writes = Mock() if shape == "invalid" else acceptance_transactions(repository_engine)
    importer = LocalFileImporter(path, raw.capture, max_bytes=1024 * 1024)
    if shape == "invalid":
        with pytest.raises(ValueError):
            import_odds_capture(
                importer,
                store,
                manifest,
                (guard,),
                odds_reference_reads(repository_engine),
                writes,
                as_of=NOW,
            )
        assert isinstance(writes, Mock)
        writes.assert_not_called()
    else:
        result = import_odds_capture(
            importer,
            store,
            manifest,
            () if shape == "empty" else (guard,),
            odds_reference_reads(repository_engine),
            writes,
            as_of=NOW,
        )
        with repository_engine.begin() as conn:
            retained = PostgresOddsCaptureRepository(conn).get(result.capture_id)
        assert retained is not None and retained.observations == ()
        replay_odds_capture(store, retained)
    assert store.get(raw.reference()) == raw.body
    with repository_engine.begin() as conn:
        assert conn.scalar(text("SELECT count(*) FROM odds_capture_quotes")) == 0
        assert conn.scalar(text("SELECT count(*) FROM odds_capture_receipts")) == (
            0 if shape == "invalid" else 1
        )
