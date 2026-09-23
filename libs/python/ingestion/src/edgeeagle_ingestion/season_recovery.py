"""Bounded portable replay artifacts; no filesystem, database, or provider access."""

from dataclasses import dataclass

from edgeeagle_domain.raw import RawPayload, RawPayloadReference, RawPayloadStore
from edgeeagle_ingestion.events import EventCandidate
from edgeeagle_ingestion.football_data import MAX_CSV_BYTES
from edgeeagle_ingestion.manifests import EventReceiptCodec
from edgeeagle_ingestion.season_bundle import (
    SeasonObjectStore,
    content_hash,
    decode_root,
    validate_digest,
    verify_bundle,
)


@dataclass
class _Objects:
    bodies: dict[str, bytes]

    def get(self, digest: str) -> bytes | None:
        return self.bodies.get(digest)

    def put(self, body: bytes) -> str:
        raise NotImplementedError("portable replay is read-only")


@dataclass
class _Raw:
    payload: RawPayload

    def get(self, reference: RawPayloadReference) -> bytes | None:
        if self.payload.reference() != reference:
            raise ValueError("raw capture differs from trusted root")
        return self.payload.body

    def put(self, payload: RawPayload) -> RawPayloadReference:
        raise NotImplementedError("portable replay is read-only")


def _root(files: dict[str, bytes], digest: str) -> bytes:
    validate_digest(digest)
    root = files.get("root.json")
    if root is None or content_hash(root) != digest:
        raise ValueError("root differs from trusted hash")
    return root


def verify_season(
    files: dict[str, bytes], digest: str, codec: EventReceiptCodec
) -> tuple[EventCandidate, ...]:
    """Verify exact membership, identity and complete replay before any writes."""
    root = _root(files, digest)
    index = decode_root(root)
    page_names = [f"page-{i:02}.json" for i in range(len(index.page_hashes))]
    if set(files) != {"root.json", "raw.bin", *page_names}:
        raise ValueError("unexpected or missing portable season member")
    raw = files["raw.bin"]
    if not isinstance(raw, bytes) or len(raw) > MAX_CSV_BYTES:
        raise ValueError("raw capture exceeds byte limit")
    objects = _Objects(dict(zip(index.page_hashes, (files[n] for n in page_names), strict=True)))
    return verify_bundle(
        root, codec, objects, _Raw(RawPayload(capture=index.raw.capture, body=raw))
    )


def export_season(
    digest: str, codec: EventReceiptCodec, objects: SeasonObjectStore, raw_store: RawPayloadStore
) -> dict[str, bytes]:
    """Read only the selected root's bounded members and verify the captured copy."""
    validate_digest(digest)
    root = objects.get(digest)
    if root is None:
        raise FileNotFoundError("retained season root is missing")
    files = {"root.json": root}
    index = decode_root(_root(files, digest))
    if index.raw.size_bytes > MAX_CSV_BYTES:
        raise ValueError("raw capture exceeds byte limit")
    for i, page in enumerate(index.page_hashes):
        body = objects.get(page)
        if body is None:
            raise FileNotFoundError("retained season page is missing")
        files[f"page-{i:02}.json"] = body
    raw = raw_store.get(index.raw)
    if raw is None:
        raise FileNotFoundError("retained raw capture is missing")
    files["raw.bin"] = raw
    verify_season(files, digest, codec)
    return files


def restore_season(
    files: dict[str, bytes],
    digest: str,
    codec: EventReceiptCodec,
    objects: SeasonObjectStore,
    raw_store: RawPayloadStore,
) -> tuple[EventCandidate, ...]:
    """Validate all bytes first, preserve raw identity, publish root last."""
    candidates = verify_season(files, digest, codec)
    root = files["root.json"]
    index = decode_root(root)
    payload = RawPayload(capture=index.raw.capture, body=files["raw.bin"])
    if raw_store.put(payload) != index.raw:
        raise ValueError("raw storage acknowledgement mismatch")
    for i, page in enumerate(index.page_hashes):
        if objects.put(files[f"page-{i:02}.json"]) != page:
            raise ValueError("page storage acknowledgement mismatch")
    if objects.put(root) != digest:
        raise ValueError("root storage acknowledgement mismatch")
    return candidates
