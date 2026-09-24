from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from edgeeagle_domain.provenance import DataSourceId
from edgeeagle_domain.raw import RawCapture, RawPayload, RawPayloadIntegrityError
from edgeeagle_ingestion.sportmonks_manifest import (
    SportmonksCaptureManifest,
    SportmonksCaptureOrigin,
    read_sportmonks_capture,
)

NOW = datetime(2026, 9, 24, 12, tzinfo=UTC)
FIXTURE = Path("tests/fixtures/providers/sportmonks/scheduled-v1/fixture.json")


def manifest(*, real: bool = False) -> SportmonksCaptureManifest:
    # All bytes and rights digests are invented, even for PROVIDER_CAPTURE tests.
    return SportmonksCaptureManifest(
        raw=RawPayload(
            capture=RawCapture(
                data_source_id=DataSourceId("sportmonks"),
                resource="/v3/football/fixtures/910001",
                ingested_at=NOW,
            ),
            body=FIXTURE.read_bytes(),
        ).reference(),
        fixture_id=910001,
        origin=SportmonksCaptureOrigin.PROVIDER_CAPTURE
        if real
        else SportmonksCaptureOrigin.AUTHORED_FIXTURE,
        captured_at=NOW if real else None,
        simulated_snapshot_at=None if real else NOW,
        rights_evidence_sha256="a" * 64 if real else None,
    )


def test_origins_keep_actual_and_simulated_evidence_separate() -> None:
    authored, real = manifest(), manifest(real=True)
    assert authored.snapshot_at == real.snapshot_at == NOW
    assert authored.usage == "SYNTHETIC_ONLY"
    assert real.usage == "REPLAY_ONLY"
    assert authored.captured_at is real.simulated_snapshot_at is None
    assert authored.raw.capture.available_at is real.raw.capture.available_at is None
    assert authored.endpoint == "/v3/football/fixtures/910001"
    assert authored.include == "participants;state"
    assert authored.timezone == "UTC"
    with pytest.raises(FrozenInstanceError):
        authored.fixture_id = 1  # type: ignore[misc]


@pytest.mark.parametrize(
    "changes",
    [
        {"raw": "untyped"},
        {"origin": "AUTHORED_FIXTURE"},
        {"fixture_id": True},
        {"fixture_id": "910001"},
        {"fixture_id": 910001.0},
        {"fixture_id": 0},
        {"fixture_id": -1},
        {"fixture_id": 2**63},
        {"include": "participants"},
        {"timezone": "Europe/London"},
        {"captured_at": NOW},
        {"simulated_snapshot_at": None},
        {"simulated_snapshot_at": NOW.replace(tzinfo=None)},
        {"rights_evidence_sha256": "a" * 64},
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
        {"rights_evidence_sha256": "A" * 64},
        {"rights_evidence_sha256": "a" * 63},
    ],
)
def test_actual_capture_requires_explicit_clock_and_rights_reference(
    changes: dict[str, Any],
) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(manifest(real=True), **changes)


def test_raw_reference_is_bounded_secret_free_and_availability_unknown() -> None:
    m = manifest()
    for raw in (
        replace(m.raw, size_bytes=1024 * 1024 + 1),
        replace(m.raw, capture=replace(m.raw.capture, available_at=NOW)),
        replace(m.raw, capture=replace(m.raw.capture, resource=m.endpoint + "?api_token=x")),
        replace(m.raw, capture=replace(m.raw.capture, resource="/v3/football/fixtures/1")),
    ):
        with pytest.raises(ValueError):
            replace(m, raw=raw)


def test_times_are_utc_without_inventing_actual_capture_time() -> None:
    offset = timezone(timedelta(hours=2))
    real = replace(manifest(real=True), captured_at=NOW.astimezone(offset))
    assert real.snapshot_at.tzinfo is UTC
    future = NOW + timedelta(days=1)
    authored = replace(manifest(), simulated_snapshot_at=future.astimezone(offset))
    assert authored.snapshot_at == future and authored.snapshot_at.tzinfo is UTC
    assert authored.captured_at is None


@pytest.mark.parametrize("real", [False, True])
def test_reader_verifies_then_parses_once_without_writes(real: bool) -> None:
    m = manifest(real=real)
    store = Mock()
    store.get.return_value = FIXTURE.read_bytes()
    result = read_sportmonks_capture(store, m)
    assert result.fixture_id == 910001
    assert result.home.participant_id == 940001
    assert result.away.participant_id == 940002
    store.get.assert_called_once_with(m.raw)
    store.put.assert_not_called()


@pytest.mark.parametrize("same_size", [False, True])
def test_corrupt_bytes_fail_before_parsing(same_size: bool) -> None:
    store = Mock()
    store.get.return_value = b"x" * (manifest().raw.size_bytes if same_size else 1)
    with pytest.raises(RawPayloadIntegrityError):
        read_sportmonks_capture(store, manifest())
    store.put.assert_not_called()


def test_missing_bytes_fail_closed() -> None:
    store = Mock()
    store.get.return_value = None
    with pytest.raises(FileNotFoundError):
        read_sportmonks_capture(store, manifest())


def test_untyped_manifest_fails_before_storage_access() -> None:
    store = Mock()
    with pytest.raises(TypeError):
        read_sportmonks_capture(store, "untyped")  # type: ignore[arg-type]
    store.get.assert_not_called()


@pytest.mark.parametrize(
    "body",
    [b"{}", FIXTURE.read_bytes().replace(b'"id": 910001', b'"id": 910002')],
)
def test_valid_digest_does_not_bypass_parser_validation(body: bytes) -> None:
    m = manifest()
    m = replace(m, raw=RawPayload(capture=m.raw.capture, body=body).reference())
    store = Mock()
    store.get.return_value = body
    with pytest.raises(ValueError):
        read_sportmonks_capture(store, m)


def test_reader_uses_manifest_snapshot_not_current_time() -> None:
    m = replace(manifest(), simulated_snapshot_at=datetime(2026, 10, 2, tzinfo=UTC))
    store = Mock()
    store.get.return_value = FIXTURE.read_bytes()
    with pytest.raises(ValueError):
        read_sportmonks_capture(store, m)
