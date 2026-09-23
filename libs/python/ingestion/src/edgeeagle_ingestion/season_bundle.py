"""ADR-029 canonical receipt pages and complete-capture replay, never eligibility."""

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from edgeeagle_domain._validation import instance
from edgeeagle_domain.raw import RawPayloadReference, RawPayloadStore
from edgeeagle_ingestion.events import EventCandidate
from edgeeagle_ingestion.football_data import (
    MAX_SEASON_ROWS,
    NORMALIZER_VERSION,
    SEASON_PARSER_VERSION,
    replay_season_results,
)
from edgeeagle_ingestion.identity import acceptance_key
from edgeeagle_ingestion.manifests import (
    EventReceiptCodec,
    _array,
    _json,
    _object,
    _pairs,
    _raw,
    _reject_number,
)

MAX_ROOT_BYTES = 65_536
MAX_PAGE_BYTES = 1_048_576
PAGE_ROWS = 64
ROOT_KIND = "FOOTBALL_DATA_SEASON_INDEX"
PAGE_KIND = "FOOTBALL_DATA_SEASON_RECEIPTS"


class SeasonObjectIntegrityError(ValueError):
    """Stored bytes or a storage acknowledgement violate the object identity."""


class SeasonObjectStore(Protocol):
    """Immutable canonical objects; get validates identity, not complete replay."""

    def put(self, body: bytes) -> str: ...

    def get(self, digest: str) -> bytes | None: ...


def content_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def validate_digest(value: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError("object identity must be a lowercase SHA-256 digest")


@dataclass(frozen=True, kw_only=True)
class SeasonIndex:
    raw: RawPayloadReference
    row_count: int
    page_hashes: tuple[str, ...]

    def __post_init__(self) -> None:
        instance(self.raw, RawPayloadReference, "raw")
        instance(self.page_hashes, tuple, "page_hashes")
        if type(self.row_count) is not int or not 1 <= self.row_count <= MAX_SEASON_ROWS:
            raise ValueError("invalid season row count")
        if len(self.page_hashes) != (self.row_count + PAGE_ROWS - 1) // PAGE_ROWS:
            raise ValueError("page count does not match row count")
        for digest in self.page_hashes:
            validate_digest(digest)
        if len(set(self.page_hashes)) != len(self.page_hashes):
            raise ValueError("duplicate page")


def _header(kind: str) -> dict[str, object]:
    return {"format": 1, "kind": kind, "usage": "REPLAY_ONLY"}


def _bounded(body: bytes, limit: int) -> bytes:
    instance(body, bytes, "body")
    if len(body) > limit:
        raise ValueError("season object exceeds byte limit")
    return body


def _load(body: bytes, limit: int, kind: str, fields: set[str]) -> dict[str, Any]:
    _bounded(body, limit)
    try:
        value = _object(
            json.loads(
                body.decode(),
                object_pairs_hook=_pairs,
                parse_float=_reject_number,
                parse_constant=_reject_number,
            ),
            {"format", "kind", "usage"} | fields,
        )
        if (
            type(value["format"]) is not int
            or value["format"] != 1
            or value["kind"] != kind
            or value["usage"] != "REPLAY_ONLY"
        ):
            raise ValueError("unsupported season object")
        return value
    except (TypeError, ValueError, RecursionError) as error:
        raise ValueError("invalid season object") from error


def encode_root(index: SeasonIndex) -> bytes:
    instance(index, SeasonIndex, "index")
    return _bounded(
        _json(
            _header(ROOT_KIND)
            | {
                "raw": asdict(index.raw),
                "row_count": index.row_count,
                "page_hashes": index.page_hashes,
                "parser_version": SEASON_PARSER_VERSION,
                "normalizer_version": NORMALIZER_VERSION,
            }
        ),
        MAX_ROOT_BYTES,
    )


def decode_root(body: bytes) -> SeasonIndex:
    value = _load(
        body,
        MAX_ROOT_BYTES,
        ROOT_KIND,
        {"raw", "row_count", "page_hashes", "parser_version", "normalizer_version"},
    )
    try:
        index = SeasonIndex(
            raw=_raw(value["raw"]),
            row_count=value["row_count"],
            page_hashes=tuple(_array(value["page_hashes"])),
        )
        if encode_root(index) != body:
            raise ValueError("noncanonical season root or unsupported versions")
        return index
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("invalid season root") from error


def _candidates(
    raw: RawPayloadReference, candidates: tuple[EventCandidate, ...], limit: int
) -> tuple[EventCandidate, ...]:
    instance(raw, RawPayloadReference, "raw")
    instance(candidates, tuple, "candidates")
    if not 1 <= len(candidates) <= limit:
        raise ValueError("invalid receipt count")
    for candidate in candidates:
        instance(candidate, EventCandidate, "candidate")
        if (
            candidate.raw != raw
            or candidate.mapping_evidence is None
            or candidate.soccer_result is None
            or candidate.parser_version != SEASON_PARSER_VERSION
            or candidate.normalizer_version != NORMALIZER_VERSION
        ):
            raise ValueError("season requires supported receipts from one capture")
    for keys in (
        [c.provider_key for c in candidates],
        [c.event.event_id for c in candidates],
        [acceptance_key(c) for c in candidates],
    ):
        if len(set(keys)) != len(candidates):
            raise ValueError("duplicate receipt identity")
    return tuple(sorted(candidates, key=lambda c: c.provider_key.provider_entity_id))


def encode_page(candidates: tuple[EventCandidate, ...], codec: EventReceiptCodec) -> bytes:
    instance(candidates, tuple, "candidates")
    if not candidates:
        raise ValueError("empty receipt page")
    instance(candidates[0], EventCandidate, "candidate")
    values = _candidates(candidates[0].raw, candidates, PAGE_ROWS)
    pins = []
    for value in values:
        encoded = codec.encode(value).encode()
        receipt = json.loads(encoded)
        codec.decode(receipt)
        pins.append(
            {
                "acceptance_key": acceptance_key(value),
                "receipt_sha256": content_hash(encoded),
                "receipt": receipt,
            }
        )
    return _bounded(_json(_header(PAGE_KIND) | {"receipts": pins}), MAX_PAGE_BYTES)


def decode_page(body: bytes, codec: EventReceiptCodec) -> tuple[EventCandidate, ...]:
    value = _load(body, MAX_PAGE_BYTES, PAGE_KIND, {"receipts"})
    try:
        values = tuple(
            codec.decode(_object(pin, {"acceptance_key", "receipt_sha256", "receipt"})["receipt"])
            for pin in _array(value["receipts"])
        )
        if encode_page(values, codec) != body:
            raise ValueError("noncanonical page or mismatched receipt pins")
        return values
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("invalid season page") from error


def build_bundle(
    raw: RawPayloadReference, candidates: tuple[EventCandidate, ...], codec: EventReceiptCodec
) -> tuple[bytes, tuple[bytes, ...]]:
    values = _candidates(raw, candidates, MAX_SEASON_ROWS)
    pages = tuple(
        encode_page(values[i : i + PAGE_ROWS], codec) for i in range(0, len(values), PAGE_ROWS)
    )
    root = encode_root(
        SeasonIndex(
            raw=raw, row_count=len(values), page_hashes=tuple(content_hash(p) for p in pages)
        )
    )
    return root, pages


def validate_object(body: bytes, codec: EventReceiptCodec) -> str:
    """Validate a root or page before storage; return full canonical-body hash."""
    _bounded(body, MAX_PAGE_BYTES)
    try:
        value = json.loads(
            body.decode(),
            object_pairs_hook=_pairs,
            parse_float=_reject_number,
            parse_constant=_reject_number,
        )
        kind = value.get("kind") if isinstance(value, dict) else None
        if kind == ROOT_KIND:
            decode_root(body)
        else:
            decode_page(body, codec)
    except (TypeError, ValueError, RecursionError) as error:
        raise ValueError("invalid season object") from error
    return content_hash(body)


def verify_bundle(
    root: bytes, codec: EventReceiptCodec, objects: SeasonObjectStore, raw_store: RawPayloadStore
) -> tuple[EventCandidate, ...]:
    index = decode_root(root)
    candidates: list[EventCandidate] = []
    pages = []
    for digest in index.page_hashes:
        body = objects.get(digest)
        if body is None:
            raise FileNotFoundError("retained season page is missing")
        _bounded(body, MAX_PAGE_BYTES)
        if content_hash(body) != digest:
            raise ValueError("season page differs from trusted hash")
        candidates.extend(decode_page(body, codec))
        pages.append(body)
    # Enforces all cross-page identities, capture agreement, count and fixed ordering.
    expected_root, expected_pages = build_bundle(index.raw, tuple(candidates), codec)
    if expected_root != root or expected_pages != tuple(pages):
        raise ValueError("season membership or partitioning mismatch")
    return replay_season_results(raw_store, index.raw, tuple(candidates))
