"""Private pinned-root discovery and fresh read-only replay inspection (ADR-031)."""

import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from edgeeagle_domain._validation import aware_datetime, instance, text
from edgeeagle_domain.raw import RawPayloadReference, RawPayloadStore
from edgeeagle_ingestion.football_data import NORMALIZER_VERSION, SEASON_PARSER_VERSION
from edgeeagle_ingestion.manifests import EventReceiptCodec
from edgeeagle_ingestion.season_bundle import (
    SeasonObjectStore,
    content_hash,
    decode_root,
    validate_digest,
    verify_bundle,
)

MAX_CATALOG_ENTRIES = 32


@dataclass(frozen=True, kw_only=True)
class CatalogEntry:
    root_hash: str
    label: str

    def __post_init__(self) -> None:
        validate_digest(self.root_hash)
        text(self.label, "label")
        if len(self.label) > 120 or any(
            unicodedata.category(c).startswith("C") for c in self.label
        ):
            raise ValueError("catalog label exceeds limit or contains control characters")


@dataclass(frozen=True, kw_only=True)
class DatasetMetadata:
    root_hash: str
    operator_label: str
    raw: RawPayloadReference
    declared_row_count: int
    page_count: int
    ineligibility_reasons: tuple[str, ...]
    parser_version: str = SEASON_PARSER_VERSION
    normalizer_version: str = NORMALIZER_VERSION
    usage: Literal["REPLAY_ONLY"] = "REPLAY_ONLY"
    backtest_eligible: Literal[False] = False


@dataclass(frozen=True, kw_only=True)
class DatasetListing:
    metadata: DatasetMetadata
    replay_status: Literal["NOT_CHECKED"] = "NOT_CHECKED"


@dataclass(frozen=True, kw_only=True)
class DatasetInspection:
    metadata: DatasetMetadata
    replay_completed_at: datetime
    receipt_count: int
    participant_count: int
    asserted_starts_at_min: datetime
    asserted_starts_at_max: datetime
    sport_ids: tuple[str, ...]
    competition_ids: tuple[str, ...]
    season_ids: tuple[str, ...]
    context_versions: tuple[str, ...]
    replay_status: Literal["VERIFIED"] = "VERIFIED"
    verification_scope: Literal["RETAINED_ARTIFACT_REPLAY"] = "RETAINED_ARTIFACT_REPLAY"
    database_acceptance_verified: Literal[False] = False
    kickoff_accuracy_verified: Literal[False] = False
    rights_verified: Literal[False] = False


def _metadata(entry: CatalogEntry, objects: SeasonObjectStore) -> tuple[DatasetMetadata, bytes]:
    root = objects.get(entry.root_hash)
    if root is None:
        raise FileNotFoundError("catalog root is missing")
    index = decode_root(root)
    if content_hash(root) != entry.root_hash:
        raise ValueError("catalog root differs from trusted hash")
    reasons: tuple[str, ...] = ("REPLAY_ONLY_CONTRACT", "CONTEXT_AVAILABILITY_UNPROVEN")
    if index.raw.capture.available_at is None:
        reasons += ("RAW_AVAILABILITY_UNKNOWN",)
    return DatasetMetadata(
        root_hash=entry.root_hash,
        operator_label=entry.label,
        raw=index.raw,
        declared_row_count=index.row_count,
        page_count=len(index.page_hashes),
        ineligibility_reasons=reasons,
    ), root


@dataclass(frozen=True)
class DatasetCatalog:
    entries: tuple[CatalogEntry, ...]

    def __post_init__(self) -> None:
        instance(self.entries, tuple, "entries")
        for entry in self.entries:
            instance(entry, CatalogEntry, "entry")
        if len(self.entries) > MAX_CATALOG_ENTRIES:
            raise ValueError("catalog exceeds entry limit")
        if len({entry.root_hash for entry in self.entries}) != len(self.entries):
            raise ValueError("duplicate catalog root")
        object.__setattr__(self, "entries", tuple(sorted(self.entries, key=lambda e: e.root_hash)))

    def list(self, objects: SeasonObjectStore) -> tuple[DatasetListing, ...]:
        """Eager all-or-error root metadata; no artifact replay or durable status."""
        return tuple(
            DatasetListing(metadata=_metadata(entry, objects)[0]) for entry in self.entries
        )

    def inspect(
        self,
        root_hash: str,
        codec: EventReceiptCodec,
        objects: SeasonObjectStore,
        raw_store: RawPayloadStore,
        *,
        clock: Callable[[], datetime],
    ) -> DatasetInspection:
        validate_digest(root_hash)
        entry = next((entry for entry in self.entries if entry.root_hash == root_hash), None)
        if entry is None:
            raise KeyError("root is not selected in this catalog")
        metadata, root = _metadata(entry, objects)
        candidates = verify_bundle(root, codec, objects, raw_store)
        completed_at = clock()
        aware_datetime(completed_at, "replay_completed_at")
        return DatasetInspection(
            metadata=metadata,
            replay_completed_at=completed_at.astimezone(UTC),
            receipt_count=len(candidates),
            participant_count=len({p.participant_id for c in candidates for p in c.entries}),
            asserted_starts_at_min=min(c.event.starts_at for c in candidates),
            asserted_starts_at_max=max(c.event.starts_at for c in candidates),
            sport_ids=tuple(sorted({c.event.sport_id.value for c in candidates})),
            competition_ids=tuple(sorted({c.event.competition_id.value for c in candidates})),
            season_ids=tuple(sorted({c.event.season_id.value for c in candidates})),
            context_versions=tuple(sorted({c.context_version for c in candidates})),
        )
