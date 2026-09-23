"""ADR-026 metadata only: no raw reads or historical eligibility claims."""

import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta, timezone
from typing import Any
from unittest.mock import Mock

import pytest

from edgeeagle_domain.sports import EventId
from edgeeagle_ingestion.manifests import (
    MAX_MANIFEST_BYTES,
    ManifestCapture,
    ReplayDatasetManifest,
    decode_manifest,
    encode_manifest,
)
from edgeeagle_persistence.receipts import EventReceiptCodec
from tests.unit.test_fixture_replay import retained

CODEC = EventReceiptCodec()


def manifest() -> ReplayDatasetManifest:
    value = retained()
    return ReplayDatasetManifest(captures=(ManifestCapture(raw=value.raw, candidates=(value,)),))


def wire(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def test_golden_mapped_identity_and_roundtrip() -> None:
    # Independently assembled from the ADR-026 recipe and preexisting receipt codec,
    # before implementing the manifest codec. Never regenerate on assertion failure.
    body = encode_manifest(manifest(), CODEC)
    envelope = json.loads(body)
    assert len(body) == 4596
    assert (
        envelope["dataset_version"]
        == "b3313e24807b50f26eec76db7ce44d0e7106e1cd65fc334e368b79bd8d72947f"
    )
    assert (
        hashlib.sha256(body).hexdigest()
        == "4e2d6cf66622c365fe061c65e864afa6fc134557a88334e136e984245cc3ff13"
    )
    assert (
        envelope["manifest"]["captures"][0]["receipts"][0]["receipt_sha256"]
        == "395b280a47cee000312316aa9a711166f48721a5671eabfbbeb4534f2f4ed363"
    )
    assert decode_manifest(body, CODEC) == manifest()
    assert encode_manifest(decode_manifest(body, CODEC), CODEC) == body
    assert manifest().usage == "REPLAY_ONLY"


def test_golden_unverified_empty_group_and_immutability() -> None:
    # A structurally empty receipt group does NOT prove the raw capture is empty.
    value = ReplayDatasetManifest(captures=(ManifestCapture(raw=retained().raw, candidates=()),))
    expected = (
        b'{"dataset_version":"d72c4e06e769a625e4d8004952dceab3b1ee65fa58c68345d67d391cdc247250",'
        b'"manifest":{"captures":[{"raw":{"capture":{"available_at":null,'
        b'"data_source_id":{"value":"synthetic-fixtures"},"effective_at":null,'
        b'"ingested_at":"2026-09-22T00:00:00+00:00","observed_at":null,'
        b'"resource":"the-odds-api-soccer-h2h-v1"},'
        b'"sha256":"271b0fcc8c5fc5729cbb03e02e94533e4652dd1109163a0e03612988111a990a",'
        b'"size_bytes":712},"receipts":[]}],"format":1,"kind":"MAPPED_EVENT_REPLAY",'
        b'"usage":"REPLAY_ONLY"}}'
    )
    assert encode_manifest(value, CODEC) == expected
    assert decode_manifest(expected, CODEC) == value
    with pytest.raises(FrozenInstanceError):
        value.captures = ()  # type: ignore[misc]


def test_builder_canonicalizes_offsets_entries_and_capture_order() -> None:
    first = retained()
    second = replace(
        first, raw=replace(first.raw, capture=replace(first.raw.capture, resource="other"))
    )
    equivalent = replace(
        first,
        event=replace(
            first.event, starts_at=first.event.starts_at.astimezone(timezone(timedelta(hours=-5)))
        ),
        entries=tuple(reversed(first.entries)),
    )
    a = ReplayDatasetManifest(
        captures=(
            ManifestCapture(raw=first.raw, candidates=(first,)),
            ManifestCapture(raw=second.raw, candidates=(second,)),
        )
    )
    b = ReplayDatasetManifest(
        captures=(
            ManifestCapture(raw=second.raw, candidates=(second,)),
            ManifestCapture(raw=first.raw, candidates=(equivalent,)),
        )
    )
    assert encode_manifest(a, CODEC) == encode_manifest(b, CODEC)


def test_projected_output_changes_version_even_when_lineage_is_identical() -> None:
    original = manifest()
    candidate = retained()
    changed = replace(candidate, event=replace(candidate.event, venue_location="Changed"))
    revised = ReplayDatasetManifest(
        captures=(ManifestCapture(raw=changed.raw, candidates=(changed,)),)
    )
    before, after = (json.loads(encode_manifest(m, CODEC)) for m in (original, revised))
    assert before["dataset_version"] != after["dataset_version"]
    assert (
        before["manifest"]["captures"][0]["receipts"][0]["acceptance_key"]
        == after["manifest"]["captures"][0]["receipts"][0]["acceptance_key"]
    )


@pytest.mark.parametrize("field", ["parser_version", "normalizer_version", "mapping_evidence"])
def test_unsupported_candidate(field: str) -> None:
    changes: dict[str, Any] = {field: None if field == "mapping_evidence" else "future"}
    value = replace(retained(), **changes)
    with pytest.raises(ValueError):
        ManifestCapture(raw=value.raw, candidates=(value,))


def test_duplicate_or_mismatched_inputs_are_not_silently_deduplicated() -> None:
    value = retained()
    capture = manifest().captures[0]
    with pytest.raises(ValueError):
        ReplayDatasetManifest(captures=())
    with pytest.raises(ValueError):
        ReplayDatasetManifest(captures=(capture, capture))
    with pytest.raises(ValueError):
        ManifestCapture(raw=value.raw, candidates=(value, value))
    with pytest.raises(ValueError):
        ManifestCapture(raw=replace(value.raw, size_bytes=0), candidates=(value,))
    second = replace(value, provider_key=replace(value.provider_key, provider_entity_id="other"))
    with pytest.raises(ValueError):
        ManifestCapture(raw=value.raw, candidates=(value, second))
    second = replace(
        value,
        event=replace(value.event, event_id=EventId("other")),
        entries=tuple(replace(e, event_id=EventId("other")) for e in value.entries),
    )
    with pytest.raises(ValueError):
        ManifestCapture(raw=value.raw, candidates=(value, second))


@pytest.mark.parametrize(
    "path,value",
    [
        (("dataset_version",), "0" * 64),
        (("extra",), True),
        (("manifest", "format"), True),
        (("manifest", "format"), 2),
        (("manifest", "kind"), "OTHER"),
        (("manifest", "usage"), "BACKTEST"),
        (("manifest", "captures"), []),
        (("manifest", "captures"), {}),
        (("manifest", "captures", 0, "extra"), True),
        (("manifest", "captures", 0, "raw", "capture", "extra"), True),
        (("manifest", "captures", 0, "raw", "size_bytes"), True),
        (
            ("manifest", "captures", 0, "raw", "capture", "available_at"),
            "2027-01-01T00:00:00+00:00",
        ),
        (("manifest", "captures", 0, "receipts", 0, "acceptance_key"), "0" * 64),
        (("manifest", "captures", 0, "receipts", 0, "receipt_sha256"), "0" * 64),
        (("manifest", "captures", 0, "receipts", 0, "receipt", "format"), 1),
    ],
)
def test_strict_reader_rejects_mutated_content(path: tuple[Any, ...], value: Any) -> None:
    envelope = json.loads(encode_manifest(manifest(), CODEC))
    target = envelope
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = value
    if path != ("dataset_version",):
        envelope["dataset_version"] = hashlib.sha256(wire(envelope["manifest"])).hexdigest()
    with pytest.raises(ValueError):
        decode_manifest(wire(envelope), CODEC)


@pytest.mark.parametrize(
    "body", [b"", b"null", b"[]", b"{}", b"\xff", b'{"x":1,"x":2}', b'{"x":NaN}', b"[" * 2000]
)
def test_malformed_wire_fails_closed(body: bytes) -> None:
    with pytest.raises(ValueError):
        decode_manifest(body, CODEC)


def test_noncanonical_wire_and_oversize_input() -> None:
    body = encode_manifest(manifest(), CODEC)
    for noncanonical in (
        body + b"\n",
        json.dumps(json.loads(body), indent=2).encode(),
        body.replace(b'"format":1', b'"format":1.0'),
    ):
        with pytest.raises(ValueError):
            decode_manifest(noncanonical, CODEC)
    codec = Mock()
    with pytest.raises(ValueError, match="limit"):
        decode_manifest(b" " * (MAX_MANIFEST_BYTES + 1), codec)
    assert codec.mock_calls == []


def test_known_availability_does_not_change_replay_only_usage() -> None:
    value = retained()
    raw = replace(
        value.raw, capture=replace(value.raw.capture, available_at=value.raw.capture.ingested_at)
    )
    model = ReplayDatasetManifest(
        captures=(ManifestCapture(raw=raw, candidates=(replace(value, raw=raw),)),)
    )
    assert decode_manifest(encode_manifest(model, CODEC), CODEC).usage == "REPLAY_ONLY"


def test_size_boundary_is_inclusive_for_builder_and_reader() -> None:
    value = retained()
    base = len(encode_manifest(manifest(), CODEC))
    version = "x" * (MAX_MANIFEST_BYTES - base + len(value.context_version))
    value = replace(value, context_version=version)
    model = ReplayDatasetManifest(captures=(ManifestCapture(raw=value.raw, candidates=(value,)),))
    body = encode_manifest(model, CODEC)
    assert len(body) == MAX_MANIFEST_BYTES
    assert decode_manifest(body, CODEC) == model
    value = replace(value, context_version=version + "x")
    model = ReplayDatasetManifest(captures=(ManifestCapture(raw=value.raw, candidates=(value,)),))
    with pytest.raises(ValueError, match="limit"):
        encode_manifest(model, CODEC)


def test_receipt_pin_order_is_canonical_and_duplicates_fail_on_wire() -> None:
    value = retained()
    second = replace(
        value,
        provider_key=replace(value.provider_key, provider_entity_id="another"),
        event=replace(value.event, event_id=EventId("another")),
        entries=tuple(replace(e, event_id=EventId("another")) for e in value.entries),
    )
    a = ReplayDatasetManifest(
        captures=(ManifestCapture(raw=value.raw, candidates=(value, second)),)
    )
    b = ReplayDatasetManifest(
        captures=(ManifestCapture(raw=value.raw, candidates=(second, value)),)
    )
    assert encode_manifest(a, CODEC) == encode_manifest(b, CODEC)
    envelope = json.loads(encode_manifest(a, CODEC))
    pins = envelope["manifest"]["captures"][0]["receipts"]
    pins.reverse()
    envelope["dataset_version"] = hashlib.sha256(wire(envelope["manifest"])).hexdigest()
    with pytest.raises(ValueError):
        decode_manifest(wire(envelope), CODEC)
    pins[1] = pins[0]
    with pytest.raises(ValueError):
        decode_manifest(wire(envelope), CODEC)


def test_value_types_are_checked() -> None:
    with pytest.raises(TypeError):
        ManifestCapture(raw=None, candidates=())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        ManifestCapture(raw=retained().raw, candidates=[])  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        ManifestCapture(raw=retained().raw, candidates=(None,))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        ReplayDatasetManifest(captures=[])  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        ReplayDatasetManifest(captures=(None,))  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        encode_manifest(None, CODEC)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        decode_manifest("{}", CODEC)  # type: ignore[arg-type]


def test_acceptance_digest_collision_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    first = retained()
    second = replace(
        first, raw=replace(first.raw, capture=replace(first.raw.capture, resource="other"))
    )
    monkeypatch.setattr("edgeeagle_ingestion.manifests.acceptance_key", lambda _: "0" * 64)
    with pytest.raises(ValueError, match="duplicate acceptance"):
        ReplayDatasetManifest(
            captures=(
                ManifestCapture(raw=first.raw, candidates=(first,)),
                ManifestCapture(raw=second.raw, candidates=(second,)),
            )
        )


def test_receipt_adapter_preserves_both_existing_formats() -> None:
    from edgeeagle_persistence._event_snapshot import encode
    from tests.unit.test_event_acceptance import candidate

    for value in (candidate(), retained()):
        assert CODEC.encode(value) == encode(value)
        assert CODEC.decode(json.loads(CODEC.encode(value))) == value


def test_all_retained_identity_components_affect_dataset_version() -> None:
    original = retained()
    evidence = original.mapping_evidence
    assert evidence is not None
    refs = evidence.references
    alternatives = (
        replace(original, context_version="new-context"),
        replace(original, raw=replace(original.raw, sha256="0" * 64)),
        replace(
            original,
            raw=replace(
                original.raw,
                capture=replace(original.raw.capture, observed_at=original.raw.capture.ingested_at),
            ),
        ),
        replace(
            original,
            mapping_evidence=replace(
                evidence,
                references=replace(
                    refs, revisions=(replace(refs.revisions[0], revision=2), *refs.revisions[1:])
                ),
            ),
        ),
        replace(
            original,
            mapping_evidence=replace(
                evidence,
                references=replace(refs, home=replace(refs.home, canonical_name="New name")),
            ),
        ),
    )
    before = json.loads(encode_manifest(manifest(), CODEC))["dataset_version"]
    for value in alternatives:
        model = ReplayDatasetManifest(
            captures=(ManifestCapture(raw=value.raw, candidates=(value,)),)
        )
        after = json.loads(encode_manifest(model, CODEC))["dataset_version"]
        assert before != after
        assert decode_manifest(encode_manifest(model, CODEC), CODEC) == model
