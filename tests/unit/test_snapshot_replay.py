"""Whole-manifest verification, with no writes or current-state lookups."""

import json
from dataclasses import replace
from unittest.mock import Mock, call

import pytest

from edgeeagle_domain.raw import RawPayload, RawPayloadIntegrityError
from edgeeagle_domain.sports import EventId
from edgeeagle_ingestion.manifests import (
    MAX_MANIFEST_BYTES,
    ManifestCapture,
    ReplayDatasetManifest,
    decode_manifest,
    encode_manifest,
)
from edgeeagle_ingestion.snapshot_replay import verify_manifest
from edgeeagle_persistence.receipts import EventReceiptCodec
from tests.unit.test_event_normalization import fixture_payload
from tests.unit.test_fixture_replay import retained

CODEC = EventReceiptCodec()


def capture(resource: str) -> tuple[RawPayload, ManifestCapture]:
    raw = fixture_payload()
    raw = replace(raw, capture=replace(raw.capture, resource=resource))
    return raw, ManifestCapture(
        raw=raw.reference(), candidates=(replace(retained(), raw=raw.reference()),)
    )


def test_all_captures_including_empty_are_read_once_without_writes() -> None:
    first_raw, first = capture("a")
    second_raw, second = capture("b")
    empty = replace(first_raw, capture=replace(first_raw.capture, resource="c"), body=b"[]")
    model = ReplayDatasetManifest(
        captures=(second, ManifestCapture(raw=empty.reference(), candidates=()), first)
    )
    body = encode_manifest(model, CODEC)
    store = Mock()
    bodies = {r.reference(): r.body for r in (first_raw, second_raw, empty)}
    store.get.side_effect = bodies.get
    result = verify_manifest(body, CODEC, store)
    assert result == (first.candidates, second.candidates, ())
    assert store.mock_calls == [
        call.get(first.raw),
        call.get(second.raw),
        call.get(empty.reference()),
    ]
    assert encode_manifest(model, CODEC) == body
    assert decode_manifest(body, CODEC).usage == "REPLAY_ONLY"
    assert all(c.raw.capture.available_at is None for group in result for c in group)


@pytest.mark.parametrize("failure", ["missing", "size", "hash", "transport", "metadata"])
def test_final_capture_failure_never_returns_a_successful_prefix(failure: str) -> None:
    raw, first = capture("a")
    later, second = capture("b")
    body = encode_manifest(ReplayDatasetManifest(captures=(first, second)), CODEC)
    store = Mock()
    failures: dict[str, bytes | None | Exception] = {
        "missing": None,
        "size": b"[]",
        "hash": b" " * len(later.body),
        "transport": OSError("storage unavailable"),
        "metadata": RawPayloadIntegrityError("capture metadata differs"),
    }
    store.get.side_effect = [raw.body, failures[failure]]
    with pytest.raises((FileNotFoundError, RawPayloadIntegrityError, OSError)):
        verify_manifest(body, CODEC, store)
    assert store.mock_calls == [call.get(first.raw), call.get(second.raw)]


@pytest.mark.parametrize("failure", ["coverage", "projection", "malformed", "labels"])
def test_structurally_valid_manifest_can_fail_artifact_verification(failure: str) -> None:
    raw, first = capture("a")
    later, second = capture("b")
    candidate = second.candidates[0]
    if failure == "coverage":
        second = replace(second, candidates=())
    elif failure == "projection":
        second = replace(
            second,
            candidates=(
                replace(candidate, event=replace(candidate.event, venue_location="Drift")),
            ),
        )
    elif failure == "malformed":
        later = replace(later, body=b"{}")
        second = ManifestCapture(raw=later.reference(), candidates=())
    else:
        assert candidate.mapping_evidence is not None
        second = replace(
            second,
            candidates=(
                replace(
                    candidate,
                    mapping_evidence=replace(candidate.mapping_evidence, home_label="Wrong"),
                ),
            ),
        )
    body = encode_manifest(ReplayDatasetManifest(captures=(first, second)), CODEC)
    assert decode_manifest(body, CODEC)
    store = Mock()
    store.get.side_effect = [raw.body, later.body]
    with pytest.raises(ValueError):
        verify_manifest(body, CODEC, store)
    assert store.mock_calls == [call.get(first.raw), call.get(second.raw)]


@pytest.mark.parametrize("failure", ["version", "pin", "noncanonical", "oversize"])
def test_entire_manifest_is_validated_before_any_raw_read(failure: str) -> None:
    _, first = capture("a")
    _, second = capture("b")
    body = encode_manifest(ReplayDatasetManifest(captures=(first, second)), CODEC)
    envelope = json.loads(body)
    pin = envelope["manifest"]["captures"][1]["receipts"][0]
    if failure == "version":
        pin["receipt"]["candidate"]["normalizer_version"] = "future"
        body = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()
    elif failure == "pin":
        pin["receipt_sha256"] = "0" * 64
        body = json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()
    elif failure == "noncanonical":
        body += b"\n"
    else:
        body = b" " * (MAX_MANIFEST_BYTES + 1)
    store = Mock()
    with pytest.raises(ValueError):
        verify_manifest(body, CODEC, store)
    assert store.mock_calls == []


def test_output_preserves_raw_event_order_not_manifest_pin_order() -> None:
    raw, group = capture("a")
    rows = json.loads(raw.body)
    rows.append(dict(rows[0], id="alphabetically-first"))
    raw = replace(raw, body=json.dumps(rows).encode())
    first = replace(group.candidates[0], raw=raw.reference())
    second = replace(
        first,
        provider_key=replace(first.provider_key, provider_entity_id="alphabetically-first"),
        event=replace(first.event, event_id=EventId("e2")),
        entries=tuple(replace(e, event_id=EventId("e2")) for e in first.entries),
    )
    group = ManifestCapture(raw=raw.reference(), candidates=(first, second))
    assert group.candidates == (second, first)
    body = encode_manifest(ReplayDatasetManifest(captures=(group,)), CODEC)
    store = Mock()
    store.get.return_value = raw.body
    assert verify_manifest(body, CODEC, store) == ((first, second),)
    assert store.mock_calls == [call.get(raw.reference())]
