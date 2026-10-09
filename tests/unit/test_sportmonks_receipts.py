import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import Mock

import pytest

from edgeeagle_domain.raw import RawPayloadIntegrityError
from edgeeagle_ingestion.sportmonks_normalization import (
    NormalizedSportmonksFixture,
    normalize_sportmonks_capture,
)
from edgeeagle_ingestion.sportmonks_receipts import (
    decode_sportmonks_receipt,
    encode_sportmonks_receipt,
    replay_sportmonks_receipt,
    sportmonks_capture_identity,
)
from tests.unit.test_sportmonks_manifest import FIXTURE, NOW
from tests.unit.test_sportmonks_normalization import inputs


def capture() -> tuple[NormalizedSportmonksFixture, Mock]:
    m, store, _, reads = inputs()
    return normalize_sportmonks_capture(store, m, reads, as_of=NOW), store


def test_receipt_round_trip_has_frozen_bytes_and_stable_identity() -> None:
    candidate, _ = capture()
    body = encode_sportmonks_receipt(candidate)
    restored = decode_sportmonks_receipt(body)

    assert restored == candidate
    assert encode_sportmonks_receipt(restored) == body
    assert hashlib.sha256(body).hexdigest() == (
        "80799727f19caddcd511fb9e3549fd3727a34121c835938be7c2bf39c90975c9"
    )
    assert sportmonks_capture_identity(candidate) == (
        "3bc7c59ef6864b77cdf536ee88f1a31b84b851e739c47be8143bba1c26440164"
    )
    assert sportmonks_capture_identity(restored) == (
        "3bc7c59ef6864b77cdf536ee88f1a31b84b851e739c47be8143bba1c26440164"
    )


def test_identity_excludes_mapping_projection_but_includes_capture_versions() -> None:
    candidate, _ = capture()
    changed_context = replace(
        candidate.references.context,
        home=replace(candidate.references.context.home, canonical_name="Other canonical name"),
    )
    changed_references = replace(candidate.references, context=changed_context)
    changed_projection = replace(candidate, references=changed_references)
    revisions = list(candidate.references.context.revisions)
    revisions[0] = replace(revisions[0], validated_by="another reviewer")
    changed_mapping = replace(
        candidate,
        references=replace(
            candidate.references,
            context=replace(candidate.references.context, revisions=tuple(revisions)),
        ),
    )

    assert sportmonks_capture_identity(changed_projection) == sportmonks_capture_identity(candidate)
    assert encode_sportmonks_receipt(changed_projection) != encode_sportmonks_receipt(candidate)
    assert sportmonks_capture_identity(changed_mapping) == sportmonks_capture_identity(candidate)
    assert encode_sportmonks_receipt(changed_mapping) != encode_sportmonks_receipt(candidate)
    with pytest.raises(ValueError, match="versions"):
        sportmonks_capture_identity(
            replace(candidate, normalizer_version="sportmonks-normalizer-v2")
        )


def test_offset_display_of_mapping_cutoff_does_not_change_canonical_receipt() -> None:
    candidate, _ = capture()
    displayed_cutoff = NOW.astimezone(timezone(timedelta(hours=5)))
    references = replace(
        candidate.references,
        context=replace(candidate.references.context, as_of=displayed_cutoff),
    )

    assert encode_sportmonks_receipt(replace(candidate, references=references)) == (
        encode_sportmonks_receipt(candidate)
    )


def test_mapping_confidence_uses_exact_canonical_decimal_text() -> None:
    candidate, _ = capture()
    revisions = list(candidate.references.context.revisions)
    revisions[0] = replace(revisions[0], confidence=Decimal("0.930000"))
    changed = replace(
        candidate,
        references=replace(
            candidate.references,
            context=replace(candidate.references.context, revisions=tuple(revisions)),
        ),
    )
    body = encode_sportmonks_receipt(changed)

    assert b'"confidence":"0.93"' in body
    assert decode_sportmonks_receipt(body) == changed


def test_receipt_sorts_entries_by_participant_id_and_preserves_mapping_order() -> None:
    candidate, _ = capture()
    body = encode_sportmonks_receipt(candidate)
    doc = json.loads(body)
    encoded_entries = doc["capture"]["references"]["entries"]
    participant_ids = [entry["participant_id"]["value"] for entry in encoded_entries]

    assert participant_ids == sorted(participant_ids)
    assert [
        row["key"]["provider_entity_type"]
        for row in doc["capture"]["references"]["context"]["revisions"]
    ] == ["sport", "league", "season", "participant", "participant"]


@pytest.mark.parametrize(
    "change", ["format", "usage", "extra", "field", "type", "tag", "version", "past_snapshot"]
)
def test_invalid_or_noncanonical_receipt_fails_closed(change: str) -> None:
    candidate, _ = capture()
    doc = json.loads(encode_sportmonks_receipt(candidate))
    if change == "format":
        doc["format"] = True
    elif change == "usage":
        doc["usage"] = "REPLAY_ONLY"
    elif change == "extra":
        doc["unexpected"] = None
    elif change == "field":
        del doc["capture"]["manifest"]["fixture_id"]
    elif change == "type":
        doc["capture"]["native"]["fixture_id"] = True
    elif change == "tag":
        doc["capture"]["references"]["source"]["$type"] = "__import__"
    elif change == "version":
        doc["capture"]["normalizer_version"] = "unknown"
    else:
        earlier = datetime(2026, 9, 23, 18, tzinfo=UTC).isoformat()
        doc["capture"]["native"]["starts_at"] = earlier
        doc["capture"]["references"]["event"]["starts_at"] = earlier

    with pytest.raises(ValueError):
        decode_sportmonks_receipt(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode())


@pytest.mark.parametrize(
    "body",
    [
        b"{}",
        b"[]",
        b'{"format":1,"format":1}',
        b"NaN",
        b" " * (8 * 1024 * 1024 + 1),
        b"[" * 1000 + b"]" * 1000,
    ],
)
def test_bad_envelopes_duplicate_keys_and_oversized_receipts_fail(body: bytes) -> None:
    with pytest.raises(ValueError):
        decode_sportmonks_receipt(body)


def test_replay_uses_retained_raw_and_candidate_context_without_resolving_again() -> None:
    candidate, store = capture()

    replayed = replay_sportmonks_receipt(
        store, decode_sportmonks_receipt(encode_sportmonks_receipt(candidate))
    )

    assert replayed == candidate
    store.get.assert_called_with(candidate.manifest.raw)
    store.put.assert_not_called()


def test_replay_detects_tampered_native_projection_and_corrupt_raw() -> None:
    candidate, store = capture()
    changed = replace(
        candidate,
        native=replace(candidate.native, home=replace(candidate.native.home, name="Other Home")),
    )
    receipt = decode_sportmonks_receipt(encode_sportmonks_receipt(changed))

    with pytest.raises(ValueError, match="replay"):
        replay_sportmonks_receipt(store, receipt)

    store.get.return_value = FIXTURE.read_bytes() + b"changed"
    with pytest.raises(RawPayloadIntegrityError):
        replay_sportmonks_receipt(store, candidate)


def test_authored_receipt_keeps_availability_unknown() -> None:
    candidate, _ = capture()

    assert candidate.manifest.raw.capture.available_at is None
    assert candidate.manifest.usage == "SYNTHETIC_ONLY"
