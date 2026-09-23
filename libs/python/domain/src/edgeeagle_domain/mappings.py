"""Immutable mapping decisions and snapshot-local resolution (ADR-013)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum

from edgeeagle_domain._validation import aware_datetime, instance, text
from edgeeagle_domain.provenance import DataSourceId, VenueId
from edgeeagle_domain.sports import CompetitionId, EventId, ParticipantId, SeasonId, SportId

CanonicalEntityId = SportId | CompetitionId | SeasonId | ParticipantId | EventId | VenueId
_TARGET_TYPES = (SportId, CompetitionId, SeasonId, ParticipantId, EventId, VenueId)


@dataclass(frozen=True, kw_only=True)
class ProviderEntityKey:
    data_source_id: DataSourceId
    provider_entity_type: str
    provider_entity_id: str

    def __post_init__(self) -> None:
        instance(self.data_source_id, DataSourceId, "data_source_id")
        text(self.provider_entity_type, "provider_entity_type")
        text(self.provider_entity_id, "provider_entity_id")


class MappingStatus(Enum):
    MAPPED = "MAPPED"
    REVOKED = "REVOKED"


@dataclass(frozen=True, kw_only=True)
class ProviderMappingRevision:
    """Recorded decision provenance, not proof of identity or review authority."""

    key: ProviderEntityKey
    revision: int
    canonical_entity_id: CanonicalEntityId
    mapping_method: str
    confidence: Decimal | None
    validated_by: str
    validated_at: datetime
    available_at: datetime
    ingested_at: datetime
    status: MappingStatus

    def __post_init__(self) -> None:
        instance(self.key, ProviderEntityKey, "key")
        if type(self.revision) is not int:
            raise TypeError("revision must be an integer, not a boolean")
        if self.revision < 1:
            raise ValueError("revision must be positive")
        if not isinstance(self.canonical_entity_id, _TARGET_TYPES):
            raise TypeError("canonical_entity_id must be a supported typed canonical ID")
        instance(self.status, MappingStatus, "status")
        text(self.mapping_method, "mapping_method")
        text(self.validated_by, "validated_by")
        if self.confidence is not None:
            instance(self.confidence, Decimal, "confidence")
            if not self.confidence.is_finite() or not 0 <= self.confidence <= 1:
                raise ValueError("confidence must be finite and within [0, 1]")
        aware_datetime(self.validated_at, "validated_at")
        aware_datetime(self.available_at, "available_at")
        aware_datetime(self.ingested_at, "ingested_at")
        if not (
            self.validated_at.astimezone(UTC)
            <= self.available_at.astimezone(UTC)
            <= self.ingested_at.astimezone(UTC)
        ):
            raise ValueError("require validated_at <= available_at <= ingested_at")


def resolve_mapping(
    key: ProviderEntityKey,
    history: Sequence[ProviderMappingRevision],
    *,
    as_of: datetime,
) -> ProviderMappingRevision | None:
    """Resolve a complete per-key history from a pinned snapshot, without I/O.

    Validate even future revisions; malformed history fails closed. None means
    absent, not yet available, or revoked. An omitted history tail is undetectable
    here; the caller owns snapshot completeness and canonical-reference checks.
    """
    instance(key, ProviderEntityKey, "key")
    instance(history, Sequence, "history")
    aware_datetime(as_of, "as_of")
    for row in history:
        instance(row, ProviderMappingRevision, "history member")
        if row.key != key:
            raise ValueError("history contains a different provider key")

    previous: ProviderMappingRevision | None = None
    selected: ProviderMappingRevision | None = None
    for expected, row in enumerate(sorted(history, key=lambda row: row.revision), start=1):
        if row.revision != expected:
            raise ValueError("history revisions must be unique and contiguous from 1")
        if previous is None:
            if row.status is not MappingStatus.MAPPED:
                raise ValueError("first revision must be MAPPED")
        else:
            if type(row.canonical_entity_id) is not type(previous.canonical_entity_id):
                raise ValueError("history cannot change canonical target type")
            if row.available_at.astimezone(UTC) < previous.available_at.astimezone(UTC):
                raise ValueError("available_at must not decrease across revisions")
            if row.ingested_at.astimezone(UTC) < previous.ingested_at.astimezone(UTC):
                raise ValueError("ingested_at must not decrease across revisions")
            if (
                row.status is MappingStatus.REVOKED
                and row.canonical_entity_id != previous.canonical_entity_id
            ):
                raise ValueError("revocation must retain the previous target")
        if row.available_at.astimezone(UTC) <= as_of.astimezone(UTC):
            selected = row
        previous = row

    if selected is None or selected.status is MappingStatus.REVOKED:
        return None
    return selected
