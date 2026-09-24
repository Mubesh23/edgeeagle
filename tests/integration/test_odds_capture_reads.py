from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection, Engine, text

from edgeeagle_api.local import market_transactions
from edgeeagle_api.main import create_app
from edgeeagle_ingestion.odds_manifest import OddsCaptureOrigin
from edgeeagle_ingestion.odds_normalization import NormalizedOddsCapture, normalize_odds_capture
from edgeeagle_persistence.odds_captures import (
    PostgresOddsCaptureReader,
    capture_identity,
    projection_rows,
)
from edgeeagle_persistence.provenance import PostgresDataSourceRepository, PostgresVenueRepository
from edgeeagle_persistence.sports import PostgresSportsRepository
from tests.integration.test_event_acceptance import seed
from tests.integration.test_repositories import repository_engine as repository_engine
from tests.unit.test_odds_manifest import NOW
from tests.unit.test_odds_normalization import inputs
from tests.unit.test_odds_receipts import receipt


def seed_odds_context(conn: Connection, capture: NormalizedOddsCapture) -> None:
    refs = capture.evidence[0].references
    seed(conn, include_source=False)
    PostgresDataSourceRepository(conn).add(refs.source)
    for venue in refs.venues:
        PostgresVenueRepository(conn).add(venue)
    PostgresSportsRepository(conn).add_event(refs.event, refs.entries)


def fixture_rows(conn: Connection, capture: NormalizedOddsCapture) -> None:
    # Test-only inserts prove readers work before application writers are enabled.
    for table, _, row in projection_rows(capture):
        conn.execute(
            text(
                f"INSERT INTO {table} ({', '.join(row)}) "
                f"VALUES ({', '.join(':' + k for k in row)}) ON CONFLICT DO NOTHING"
            ),
            row,
        )


@pytest.mark.parametrize("declared_capture", [False, True])
def test_odds_capture_readback_and_api_pagination(
    repository_engine: Engine, declared_capture: bool
) -> None:
    capture, _, _ = receipt()
    if declared_capture:
        # Invented evidence exercises the branch; no actual provider rights claimed.
        manifest, guard, _, store, _, reads = inputs()
        manifest = replace(
            manifest,
            origin=OddsCaptureOrigin.PROVIDER_CAPTURE,
            captured_at=NOW,
            simulated_snapshot_at=None,
            rights_evidence_sha256="b" * 64,
            settlement_profiles=tuple(
                replace(p, origin=OddsCaptureOrigin.PROVIDER_CAPTURE)
                for p in manifest.settlement_profiles
            ),
        )
        capture = normalize_odds_capture(store, manifest, (guard,), reads, as_of=NOW)
    with repository_engine.begin() as conn:
        seed_odds_context(conn, capture)
        fixture_rows(conn, capture)
        assert PostgresOddsCaptureReader(conn).get(capture_identity(capture)) == capture
    market = capture.observations[0].market.market_id.value
    with TestClient(create_app(market_reads=market_transactions(repository_engine))) as client:
        first = client.get(f"/v1/markets/{market}/quotes", params={"limit": 2})
        assert first.status_code == 200
        data = first.json()
        assert len(data["items"]) == 2
        following = client.get(
            f"/v1/markets/{market}/quotes", params={"after_quote_id": data["next_after_quote_id"]}
        ).json()
        prices = data["items"] + following["items"]
        assert len(prices) == 3
        assert {p["odds_decimal"] for p in prices} == {
            "2.12345678901234567890123456789",
            "3.2",
            "3.4",
        }
        for price in prices:
            provenance = price["provenance"]
            assert provenance["origin"] == (
                "PROVIDER_CAPTURE" if declared_capture else "AUTHORED_FIXTURE"
            )
            assert provenance["usage"] == ("REPLAY_ONLY" if declared_capture else "SYNTHETIC_ONLY")
            assert len(provenance["mapping_revisions"]) == 3
            assert provenance["bookmaker_updated_at"] is not None
            assert provenance["market_updated_at"] is None
            assert price["available_at"] is None
