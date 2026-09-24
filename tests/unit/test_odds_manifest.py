from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from edgeeagle_domain.markets import MarketPeriod
from edgeeagle_domain.provenance import DataSourceId
from edgeeagle_domain.raw import RawCapture, RawPayload, RawPayloadIntegrityError
from edgeeagle_ingestion.odds_manifest import (
    OddsCaptureManifest,
    OddsCaptureOrigin,
    OddsSettlementProfile,
    read_odds_capture,
)

NOW = datetime(2026, 9, 23, 12, tzinfo=UTC)


def manifest(*, real: bool = False) -> OddsCaptureManifest:
    # Every byte and evidence digest in these tests is invented, including tests
    # of the PROVIDER_CAPTURE branch. No actual provider approval is claimed.
    origin = OddsCaptureOrigin.PROVIDER_CAPTURE if real else OddsCaptureOrigin.AUTHORED_FIXTURE
    raw = RawPayload(
        capture=RawCapture(
            data_source_id=DataSourceId("odds-api"),
            resource="/v4/sports/soccer_epl/odds",
            ingested_at=NOW,
        ),
        body=b"[]",
    ).reference()
    profile = OddsSettlementProfile(
        bookmaker_key="bovada",
        version="authored-test-v1",
        origin=origin,
        period=MarketPeriod.REGULATION_TIME,
        evidence_sha256="a" * 64,
    )
    return OddsCaptureManifest(
        raw=raw,
        sport_key="soccer_epl",
        origin=origin,
        captured_at=NOW if real else None,
        simulated_snapshot_at=None if real else NOW,
        rights_evidence_sha256="b" * 64 if real else None,
        settlement_profiles=(profile,),
    )


def test_fixture_and_capture_have_distinct_usage_and_clock_evidence() -> None:
    authored, real = manifest(), manifest(real=True)
    assert authored.snapshot_at == real.snapshot_at == NOW
    assert authored.usage == "SYNTHETIC_ONLY"
    assert real.usage == "REPLAY_ONLY"
    assert authored.captured_at is None
    assert real.simulated_snapshot_at is None
    assert authored.raw.capture.available_at is real.raw.capture.available_at is None
    assert authored.endpoint == "/v4/sports/soccer_epl/odds"
    assert authored.market == "h2h"
    assert authored.odds_format == "decimal"
    assert authored.date_format == "iso"


@pytest.mark.parametrize(
    "changes",
    [
        {"origin": "AUTHORED_FIXTURE"},
        {"captured_at": NOW},
        {"simulated_snapshot_at": None},
        {"simulated_snapshot_at": NOW.replace(tzinfo=None)},
        {"rights_evidence_sha256": "b" * 64},
        {"sport_key": "basketball_nba"},
        {"sport_key": "soccer_epl?apiKey=secret"},
        {"sport_key": "soccer_" + "x" * 256},
        {"market": "h2h_lay"},
        {"odds_format": "american"},
        {"date_format": "unix"},
        {"settlement_profiles": ()},
        {"settlement_profiles": []},
        {"settlement_profiles": ("untyped",)},
        {"raw": "untyped"},
    ],
)
def test_invalid_manifest_fails_closed(changes: dict[str, Any]) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(manifest(), **changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"captured_at": None},
        {"captured_at": NOW.replace(tzinfo=None)},
        {"captured_at": NOW + timedelta(seconds=1)},
        {"simulated_snapshot_at": NOW},
        {"rights_evidence_sha256": None},
        {"rights_evidence_sha256": ""},
        {"rights_evidence_sha256": "B" * 64},
    ],
)
def test_real_capture_requires_explicit_rights_reference_and_actual_clock(
    changes: dict[str, Any],
) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(manifest(real=True), **changes)


@pytest.mark.parametrize(
    "changes",
    [
        {"bookmaker_key": ""},
        {"bookmaker_key": "bovada?apiKey=secret"},
        {"bookmaker_key": "x" * 65},
        {"version": ""},
        {"version": "v1\n"},
        {"version": "v" * 65},
        {"origin": "PROVIDER_CAPTURE"},
        {"period": "REGULATION_TIME"},
        {"evidence_sha256": "not-a-digest"},
        {"evidence_sha256": None},
    ],
)
def test_profile_requires_explicit_bounded_versioned_evidence(changes: dict[str, Any]) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(manifest().settlement_profiles[0], **changes)


def test_profiles_must_be_unique_bounded_and_match_capture_origin() -> None:
    m = manifest()
    profile = m.settlement_profiles[0]
    for profiles in (
        (profile, profile),
        tuple(replace(profile, bookmaker_key=f"book_{i}") for i in range(21)),
        (replace(profile, origin=OddsCaptureOrigin.PROVIDER_CAPTURE),),
    ):
        with pytest.raises(ValueError):
            replace(m, settlement_profiles=profiles)
    second = replace(profile, bookmaker_key="another_book")
    assert replace(m, settlement_profiles=(profile, second)).settlement_profiles == (
        second,
        profile,
    )


def test_raw_reference_is_bounded_sanitized_and_availability_stays_unknown() -> None:
    m = manifest()
    for raw in (
        replace(m.raw, size_bytes=1024 * 1024 + 1),
        replace(m.raw, capture=replace(m.raw.capture, available_at=NOW)),
        replace(m.raw, capture=replace(m.raw.capture, resource=m.endpoint + "?apiKey=secret")),
    ):
        with pytest.raises(ValueError):
            replace(m, raw=raw)


def test_times_are_utc_and_simulated_clock_is_not_misrepresented_as_capture_time() -> None:
    offset = timezone(timedelta(hours=2))
    real = replace(manifest(real=True), captured_at=NOW.astimezone(offset))
    assert real.captured_at == NOW and real.captured_at.tzinfo is UTC
    future = NOW + timedelta(days=1)
    authored = replace(manifest(), simulated_snapshot_at=future.astimezone(offset))
    assert authored.snapshot_at == future and authored.snapshot_at.tzinfo is UTC
    assert authored.captured_at is None


def test_empty_capture_is_retained_and_read_once_without_writes() -> None:
    m = manifest()
    store = Mock()
    store.get.return_value = b"[]"
    assert read_odds_capture(store, m) == ()
    store.get.assert_called_once_with(m.raw)
    store.put.assert_not_called()


@pytest.mark.parametrize("body", [b"{}", b"[ ]"])
def test_corrupt_retained_bytes_fail_before_parsing(body: bytes) -> None:
    store = Mock()
    store.get.return_value = body
    with pytest.raises(RawPayloadIntegrityError):
        read_odds_capture(store, manifest())


def test_missing_retained_bytes_fail_closed() -> None:
    store = Mock()
    store.get.return_value = None
    with pytest.raises(FileNotFoundError):
        read_odds_capture(store, manifest())


def test_declared_bookmaker_profiles_are_enforced_on_full_payload() -> None:
    body = Path("tests/fixtures/providers/the_odds_api/pre-match-v1/odds-success.json").read_bytes()
    m = manifest()
    m = replace(m, raw=RawPayload(capture=m.raw.capture, body=body).reference())
    store = Mock()
    store.get.return_value = body
    events = read_odds_capture(store, m)
    assert len(events) == 1
    assert events[0].bookmakers[0].bookmaker_key == "bovada"
    changed = replace(
        m,
        settlement_profiles=(replace(m.settlement_profiles[0], bookmaker_key="other_book"),),
    )
    with pytest.raises(ValueError, match="undeclared bookmaker"):
        read_odds_capture(store, changed)
    store.put.assert_not_called()


def test_valid_digest_does_not_make_malformed_payload_valid() -> None:
    m = manifest()
    body = b"{}"
    m = replace(m, raw=RawPayload(capture=m.raw.capture, body=body).reference())
    store = Mock()
    store.get.return_value = body
    with pytest.raises(ValueError):
        read_odds_capture(store, m)
