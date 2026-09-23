"""Immutable mapping history with per-key compare-and-append and replay checks."""

from dataclasses import replace
from datetime import UTC, datetime

from sqlalchemy import Connection, RowMapping, text

from edgeeagle_domain._validation import aware_datetime, instance
from edgeeagle_domain.mapping_repository import MappingConflictError
from edgeeagle_domain.mappings import (
    CanonicalEntityId,
    MappingStatus,
    ProviderEntityKey,
    ProviderMappingRevision,
    resolve_mapping,
)
from edgeeagle_domain.provenance import VenueId
from edgeeagle_domain.sports import CompetitionId, EventId, ParticipantId, SeasonId, SportId
from edgeeagle_persistence._transactions import insert, require_transaction

_TARGETS: dict[str, tuple[type[CanonicalEntityId], str]] = {
    "SPORT": (SportId, "sport_id"),
    "COMPETITION": (CompetitionId, "competition_id"),
    "SEASON": (SeasonId, "season_id"),
    "PARTICIPANT": (ParticipantId, "participant_id"),
    "EVENT": (EventId, "event_id"),
    "VENUE": (VenueId, "venue_id"),
}
_KEY_WHERE = (
    "data_source_id = :source AND provider_entity_type = :provider_type "
    "AND provider_entity_id = :provider_id"
)


def _key_parameters(key: ProviderEntityKey) -> dict[str, str]:
    return {
        "source": key.data_source_id.value,
        "provider_type": key.provider_entity_type,
        "provider_id": key.provider_entity_id,
    }


def _utc(row: ProviderMappingRevision) -> ProviderMappingRevision:
    # Datetime equality alone is insufficient around folds with different tzinfo objects.
    return replace(
        row,
        validated_at=row.validated_at.astimezone(UTC),
        available_at=row.available_at.astimezone(UTC),
        ingested_at=row.ingested_at.astimezone(UTC),
    )


def _decode(key: ProviderEntityKey, row: RowMapping) -> ProviderMappingRevision:
    target_class, column = _TARGETS[row["target_kind"]]
    return _utc(
        ProviderMappingRevision(
            key=key,
            revision=row["revision"],
            canonical_entity_id=target_class(row[column]),
            mapping_method=row["mapping_method"],
            confidence=row["confidence"],
            validated_by=row["validated_by"],
            validated_at=row["validated_at"],
            available_at=row["available_at"],
            ingested_at=row["ingested_at"],
            status=MappingStatus(row["status"]),
        )
    )


class PostgresMappingRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def history(self, key: ProviderEntityKey) -> tuple[ProviderMappingRevision, ...]:
        instance(key, ProviderEntityKey, "key")
        require_transaction(self._connection)
        rows = self._connection.execute(
            text(
                "SELECT revision, target_kind, sport_id, competition_id, season_id, "
                "participant_id, "
                "event_id, venue_id, mapping_method, confidence, validated_by, validated_at, "
                "available_at, ingested_at, status FROM provider_mapping_revisions WHERE "
                + _KEY_WHERE
                + " ORDER BY revision"
            ),
            _key_parameters(key),
        ).mappings()
        history = tuple(_decode(key, row) for row in rows)
        resolve_mapping(key, history, as_of=datetime.max.replace(tzinfo=UTC))
        return history

    def resolve(self, key: ProviderEntityKey, *, as_of: datetime) -> ProviderMappingRevision | None:
        aware_datetime(as_of, "as_of")
        return resolve_mapping(key, self.history(key), as_of=as_of)

    def append(self, revision: ProviderMappingRevision) -> ProviderMappingRevision:
        instance(revision, ProviderMappingRevision, "revision")
        candidate = _utc(revision)
        require_transaction(self._connection)
        if self._connection.get_isolation_level() != "READ COMMITTED":
            raise ValueError("Mapping append requires READ COMMITTED isolation")
        kind, column = next(
            (kind, column)
            for kind, (target, column) in _TARGETS.items()
            if isinstance(candidate.canonical_entity_id, target)
        )
        params = _key_parameters(candidate.key)
        with insert(self._connection):
            # DO NOTHING avoids the immutable-key UPDATE trigger, including on first-write races.
            self._connection.execute(
                text(
                    "INSERT INTO provider_mapping_keys "
                    "(data_source_id, provider_entity_type, provider_entity_id, target_kind) "
                    "VALUES (:source, :provider_type, :provider_id, :kind) "
                    "ON CONFLICT (data_source_id, provider_entity_type, provider_entity_id) "
                    "DO NOTHING"
                ),
                params | {"kind": kind},
            )
            stored_kind = self._connection.execute(
                text(
                    "SELECT target_kind FROM provider_mapping_keys WHERE "
                    + _KEY_WHERE
                    + " FOR UPDATE"
                ),
                params,
            ).scalar_one()
            history = self.history(candidate.key)
            if candidate.revision <= len(history):
                stored = history[candidate.revision - 1]
                if stored != candidate:
                    raise MappingConflictError("Revision identity already has different content")
                return stored
            if candidate.revision != len(history) + 1:
                raise MappingConflictError("Proposed revision is not the next revision")
            if kind != stored_kind:
                raise ValueError("Mapping history cannot change canonical target type")
            resolve_mapping(candidate.key, (*history, candidate), as_of=candidate.available_at)
            values: dict[str, object] = {
                **params,
                "revision": candidate.revision,
                "kind": kind,
                **{target_column: None for _, target_column in _TARGETS.values()},
                column: candidate.canonical_entity_id.value,
                "method": candidate.mapping_method,
                "confidence": candidate.confidence,
                "actor": candidate.validated_by,
                "validated": candidate.validated_at,
                "available": candidate.available_at,
                "ingested": candidate.ingested_at,
                "status": candidate.status.value,
            }
            self._connection.execute(
                text(
                    "INSERT INTO provider_mapping_revisions "
                    "(data_source_id, provider_entity_type, provider_entity_id, "
                    "revision, target_kind, "
                    "sport_id, competition_id, season_id, participant_id, event_id, venue_id, "
                    "mapping_method, confidence, validated_by, validated_at, "
                    "available_at, ingested_at, status) "
                    "VALUES (:source, :provider_type, :provider_id, :revision, :kind, "
                    ":sport_id, :competition_id, :season_id, :participant_id, "
                    ":event_id, :venue_id, "
                    ":method, :confidence, :actor, :validated, :available, :ingested, :status)"
                ),
                values,
            )
            return candidate
