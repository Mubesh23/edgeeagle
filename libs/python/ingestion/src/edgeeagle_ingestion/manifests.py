"""Bounded replay-only metadata (ADR-026); no storage or eligibility verification."""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal, NoReturn, Protocol

from edgeeagle_domain._validation import instance
from edgeeagle_domain.provenance import DataSourceId
from edgeeagle_domain.raw import RawCapture, RawPayloadReference
from edgeeagle_ingestion.events import EventCandidate
from edgeeagle_ingestion.football_data import NORMALIZER_VERSION, PARSER_VERSION
from edgeeagle_ingestion.identity import acceptance_key, lineage_json_value

MAX_MANIFEST_BYTES = 1_048_576


class EventReceiptCodec(Protocol):
    """Pure existing receipt serialization; implementations must preserve format bytes."""

    def encode(self, candidate: EventCandidate) -> str: ...

    def decode(self, snapshot: object) -> EventCandidate: ...


def _json(value: object) -> bytes:
    return json.dumps(
        value, default=lineage_json_value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


@dataclass(frozen=True, kw_only=True)
class ManifestCapture:
    raw: RawPayloadReference
    candidates: tuple[EventCandidate, ...]

    def __post_init__(self) -> None:
        instance(self.raw, RawPayloadReference, "raw")
        instance(self.candidates, tuple, "candidates")
        for candidate in self.candidates:
            instance(candidate, EventCandidate, "candidate")
            versions = (candidate.parser_version, candidate.normalizer_version)
            supported = (
                ("synthetic-odds-events-v1", "synthetic-event-mappings-v1")
                if candidate.soccer_result is None
                else (PARSER_VERSION, NORMALIZER_VERSION)
            )
            if candidate.mapping_evidence is None or versions != supported:
                raise ValueError("manifest requires supported mapped receipts")
            if candidate.raw != self.raw:
                raise ValueError("candidate must share its capture's raw reference")
        if len({c.provider_key for c in self.candidates}) != len(self.candidates) or len(
            {c.event.event_id for c in self.candidates}
        ) != len(self.candidates):
            raise ValueError("duplicate provider or canonical event identity within capture")
        object.__setattr__(
            self,
            "candidates",
            tuple(sorted(self.candidates, key=lambda c: _json(asdict(c.provider_key)))),
        )


@dataclass(frozen=True, kw_only=True)
class ReplayDatasetManifest:
    """Structurally valid inputs; not proof of acceptance, raw coverage, or availability."""

    captures: tuple[ManifestCapture, ...]
    usage: Literal["REPLAY_ONLY"] = field(default="REPLAY_ONLY", init=False)
    kind: Literal["MAPPED_EVENT_REPLAY", "FOOTBALL_DATA_RESULTS_REPLAY"] = field(
        default="MAPPED_EVENT_REPLAY", init=False
    )

    def __post_init__(self) -> None:
        instance(self.captures, tuple, "captures")
        if not self.captures:
            raise ValueError("manifest requires at least one capture")
        for capture in self.captures:
            instance(capture, ManifestCapture, "capture")
        if any(c.soccer_result is not None for group in self.captures for c in group.candidates):
            if any(
                not group.candidates or any(c.soccer_result is None for c in group.candidates)
                for group in self.captures
            ):
                raise ValueError("CSV manifests require nonempty, unmixed result captures")
            object.__setattr__(self, "kind", "FOOTBALL_DATA_RESULTS_REPLAY")
        raw_keys = [_json(asdict(c.raw)) for c in self.captures]
        if len(set(raw_keys)) != len(raw_keys):
            raise ValueError("duplicate raw capture")
        keys = [acceptance_key(c) for group in self.captures for c in group.candidates]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate acceptance key")
        object.__setattr__(
            self, "captures", tuple(sorted(self.captures, key=lambda c: _json(asdict(c.raw))))
        )


def encode_manifest(manifest: ReplayDatasetManifest, codec: EventReceiptCodec) -> bytes:
    """Build canonical pins/envelope; never verify or acquire raw artifacts."""
    instance(manifest, ReplayDatasetManifest, "manifest")
    captures = []
    for capture in manifest.captures:
        pins = []
        for candidate in capture.candidates:
            receipt_bytes = codec.encode(candidate).encode("utf-8")
            receipt = json.loads(receipt_bytes)
            # Keep nested receipt validation/representation owned by the existing codec.
            codec.decode(receipt)
            pins.append(
                {
                    "acceptance_key": acceptance_key(candidate),
                    "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
                    "receipt": receipt,
                }
            )
        captures.append({"raw": asdict(capture.raw), "receipts": pins})
    content = {
        "format": 1,
        "kind": manifest.kind,
        "usage": manifest.usage,
        "captures": captures,
    }
    result = _json(
        {"dataset_version": hashlib.sha256(_json(content)).hexdigest(), "manifest": content}
    )
    if len(result) > MAX_MANIFEST_BYTES:
        raise ValueError("manifest exceeds byte limit")
    return result


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_number(value: str) -> NoReturn:
    raise ValueError("manifest does not permit floating point or nonstandard numbers")


def _object(value: Any, fields: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("invalid manifest object fields")
    return value


def _array(value: Any) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError("manifest array required")
    return value


def _raw(value: Any) -> RawPayloadReference:
    raw = _object(value, {"capture", "sha256", "size_bytes"})
    capture = _object(
        raw["capture"],
        {
            "data_source_id",
            "resource",
            "ingested_at",
            "effective_at",
            "observed_at",
            "available_at",
        },
    )
    source = _object(capture["data_source_id"], {"value"})
    return RawPayloadReference(
        capture=RawCapture(
            data_source_id=DataSourceId(source["value"]),
            resource=capture["resource"],
            ingested_at=datetime.fromisoformat(capture["ingested_at"]),
            effective_at=_time(capture["effective_at"]),
            observed_at=_time(capture["observed_at"]),
            available_at=_time(capture["available_at"]),
        ),
        sha256=raw["sha256"],
        size_bytes=raw["size_bytes"],
    )


def _time(value: Any) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def decode_manifest(body: bytes, codec: EventReceiptCodec) -> ReplayDatasetManifest:
    """Reject noncanonical bytes or stale pins; success is structural validation only."""
    instance(body, bytes, "body")
    if len(body) > MAX_MANIFEST_BYTES:
        raise ValueError("manifest exceeds byte limit")
    try:
        envelope = _object(
            json.loads(
                body.decode("utf-8"),
                object_pairs_hook=_pairs,
                parse_constant=_reject_number,
                parse_float=_reject_number,
            ),
            {"dataset_version", "manifest"},
        )
        content = _object(envelope["manifest"], {"format", "kind", "usage", "captures"})
        if (
            type(content["format"]) is not int
            or content["format"] != 1
            or content["kind"] not in ("MAPPED_EVENT_REPLAY", "FOOTBALL_DATA_RESULTS_REPLAY")
            or content["usage"] != "REPLAY_ONLY"
        ):
            raise ValueError("unsupported manifest format, kind, or usage")
        captures = []
        for item in _array(content["captures"]):
            capture = _object(item, {"raw", "receipts"})
            candidates = []
            for item in _array(capture["receipts"]):
                pin = _object(item, {"acceptance_key", "receipt_sha256", "receipt"})
                candidates.append(codec.decode(pin["receipt"]))
            captures.append(ManifestCapture(raw=_raw(capture["raw"]), candidates=tuple(candidates)))
        result = ReplayDatasetManifest(captures=tuple(captures))
        # Recompute every receipt hash, acceptance key, and dataset version. This
        # also enforces canonical ordering/encoding without repairing stored pins.
        if encode_manifest(result, codec) != body:
            raise ValueError("noncanonical manifest or mismatched content pins")
        return result
    except (ValueError, TypeError, KeyError, RecursionError) as error:
        raise ValueError("Invalid replay dataset manifest") from error
