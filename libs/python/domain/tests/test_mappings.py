"""Historical mapping choices must not silently use future corrections."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from edgeeagle_domain.mappings import (
    MappingStatus,
    ProviderEntityKey,
    ProviderMappingRevision,
    resolve_mapping,
)
from edgeeagle_domain.provenance import DataSourceId, VenueId
from edgeeagle_domain.sports import CompetitionId, EventId, ParticipantId, SeasonId, SportId

NOW = datetime(2026, 9, 22, tzinfo=UTC)
KEY = ProviderEntityKey(
    data_source_id=DataSourceId("source"), provider_entity_type="team", provider_entity_id="001"
)


@pytest.fixture
def mapping() -> ProviderMappingRevision:
    return ProviderMappingRevision(
        key=KEY,
        revision=1,
        canonical_entity_id=ParticipantId("a"),
        mapping_method="manual-review-v1",
        confidence=None,
        validated_by="fixture-reviewer",
        validated_at=NOW,
        available_at=NOW,
        ingested_at=NOW,
        status=MappingStatus.MAPPED,
    )


def test_correction_revocation_and_restore(mapping: ProviderMappingRevision) -> None:
    corrected = replace(
        mapping,
        revision=2,
        canonical_entity_id=ParticipantId("b"),
        available_at=NOW + timedelta(hours=1),
        ingested_at=NOW + timedelta(hours=1),
    )
    revoked = replace(
        corrected,
        revision=3,
        status=MappingStatus.REVOKED,
        available_at=NOW + timedelta(hours=2),
        ingested_at=NOW + timedelta(hours=2),
    )
    restored = replace(
        revoked,
        revision=4,
        status=MappingStatus.MAPPED,
        available_at=NOW + timedelta(hours=3),
        ingested_at=NOW + timedelta(hours=3),
    )
    history = (restored, mapping, revoked, corrected)
    assert resolve_mapping(KEY, history, as_of=NOW - timedelta(seconds=1)) is None
    assert resolve_mapping(KEY, history, as_of=NOW) == mapping
    assert resolve_mapping(KEY, history, as_of=corrected.available_at) == corrected
    assert resolve_mapping(KEY, history, as_of=revoked.available_at) is None
    assert resolve_mapping(KEY, history, as_of=restored.available_at) == restored
    assert mapping.canonical_entity_id == ParticipantId("a")


def test_empty_history_and_equal_timestamp_tie(mapping: ProviderMappingRevision) -> None:
    assert resolve_mapping(KEY, (), as_of=NOW) is None
    next_revision = replace(mapping, revision=2, confidence=Decimal("0"))
    assert resolve_mapping(KEY, (next_revision, mapping), as_of=NOW) == next_revision


@pytest.mark.parametrize(
    "field,value",
    [
        ("data_source_id", DataSourceId("other")),
        ("provider_entity_type", "player"),
        ("provider_entity_id", "1"),
    ],
)
def test_namespaces_do_not_collide(
    mapping: ProviderMappingRevision, field: str, value: Any
) -> None:
    other_key = replace(KEY, **{field: value})
    with pytest.raises(ValueError, match="key"):
        resolve_mapping(other_key, (mapping,), as_of=NOW)


@pytest.mark.parametrize(
    "kind", [SportId, CompetitionId, SeasonId, ParticipantId, EventId, VenueId]
)
def test_existing_canonical_target_types(mapping: ProviderMappingRevision, kind: Any) -> None:
    row = replace(mapping, canonical_entity_id=kind("canonical"))
    assert resolve_mapping(KEY, (row,), as_of=NOW) == row


@pytest.mark.parametrize(
    "changes,error",
    [
        ({"key": "raw"}, TypeError),
        ({"revision": True}, TypeError),
        ({"revision": 1.0}, TypeError),
        ({"revision": 0}, ValueError),
        ({"canonical_entity_id": DataSourceId("source")}, TypeError),
        ({"canonical_entity_id": "provider-id"}, TypeError),
        ({"status": "MAPPED"}, TypeError),
        ({"confidence": 0.5}, TypeError),
        ({"confidence": Decimal("NaN")}, ValueError),
        ({"confidence": Decimal("Infinity")}, ValueError),
        ({"confidence": Decimal("-0.1")}, ValueError),
        ({"confidence": Decimal("1.1")}, ValueError),
        ({"validated_by": ""}, ValueError),
        ({"mapping_method": " padded"}, ValueError),
        ({"validated_at": NOW + timedelta(seconds=1)}, ValueError),
        ({"ingested_at": NOW - timedelta(seconds=1)}, ValueError),
    ],
)
def test_invalid_revision_fields(
    mapping: ProviderMappingRevision, changes: dict[str, Any], error: type[Exception]
) -> None:
    with pytest.raises(error):
        replace(mapping, **changes)


@pytest.mark.parametrize("field", ["validated_at", "available_at", "ingested_at"])
def test_naive_timestamps_rejected(mapping: ProviderMappingRevision, field: str) -> None:
    changes: dict[str, Any] = {field: NOW.replace(tzinfo=None)}
    with pytest.raises(ValueError, match=field):
        replace(mapping, **changes)


@pytest.mark.parametrize("confidence", [None, Decimal("0"), Decimal("0.5"), Decimal("1")])
def test_confidence_is_not_an_approval_threshold(
    mapping: ProviderMappingRevision, confidence: Decimal | None
) -> None:
    row = replace(mapping, confidence=confidence)
    assert resolve_mapping(KEY, (row,), as_of=NOW) == row


@pytest.mark.parametrize(
    "change,message",
    [
        ({"revision": 1}, "contiguous"),
        ({"revision": 3}, "contiguous"),
        ({"canonical_entity_id": EventId("a")}, "target type"),
        (
            {
                "available_at": NOW - timedelta(seconds=1),
                "validated_at": NOW - timedelta(seconds=1),
            },
            "available_at",
        ),
        (
            {"status": MappingStatus.REVOKED, "canonical_entity_id": ParticipantId("b")},
            "revocation",
        ),
    ],
)
def test_invalid_histories(
    mapping: ProviderMappingRevision, change: dict[str, Any], message: str
) -> None:
    later = replace(mapping, revision=2)
    with pytest.raises(ValueError, match=message):
        resolve_mapping(KEY, (mapping, replace(later, **change)), as_of=NOW)


def test_incomplete_history_and_initial_revocation_fail(mapping: ProviderMappingRevision) -> None:
    with pytest.raises(ValueError, match="contiguous"):
        resolve_mapping(KEY, (replace(mapping, revision=2),), as_of=NOW)
    with pytest.raises(ValueError, match="first revision"):
        resolve_mapping(KEY, (replace(mapping, status=MappingStatus.REVOKED),), as_of=NOW)


def test_ingestion_order_and_late_ingestion(mapping: ProviderMappingRevision) -> None:
    late = replace(mapping, ingested_at=NOW + timedelta(days=1))
    assert resolve_mapping(KEY, (late,), as_of=NOW) == late
    with pytest.raises(ValueError, match="ingested_at"):
        resolve_mapping(KEY, (late, replace(mapping, revision=2)), as_of=NOW)


def test_immutability(mapping: ProviderMappingRevision) -> None:
    for record, field in [(mapping, "revision"), (KEY, "provider_entity_id")]:
        with pytest.raises(FrozenInstanceError):
            setattr(record, field, "changed")


@pytest.mark.parametrize(
    "field,value",
    [
        ("data_source_id", VenueId("venue")),
        ("provider_entity_type", ""),
        ("provider_entity_id", " padded "),
    ],
)
def test_invalid_keys(field: str, value: Any) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(KEY, **{field: value})


def test_resolver_input_validation(mapping: ProviderMappingRevision) -> None:
    with pytest.raises(ValueError, match="as_of"):
        resolve_mapping(KEY, (mapping,), as_of=NOW.replace(tzinfo=None))
    with pytest.raises(TypeError):
        resolve_mapping(KEY, (None,), as_of=NOW)  # type: ignore[arg-type]


def test_dst_fold_uses_actual_availability_instant(mapping: ProviderMappingRevision) -> None:
    first = datetime(2026, 11, 1, 1, 30, tzinfo=ZoneInfo("America/New_York"), fold=0)
    second = first.replace(fold=1)
    row = replace(mapping, validated_at=first, available_at=second, ingested_at=second)
    assert resolve_mapping(KEY, (row,), as_of=first) is None
    assert resolve_mapping(KEY, (row,), as_of=second) == row
    with pytest.raises(ValueError, match="validated_at"):
        replace(row, validated_at=second, available_at=first)


def test_bad_future_revision_fails_closed(mapping: ProviderMappingRevision) -> None:
    future = replace(
        mapping,
        revision=3,
        available_at=NOW + timedelta(days=1),
        ingested_at=NOW + timedelta(days=1),
    )
    with pytest.raises(ValueError, match="contiguous"):
        resolve_mapping(KEY, (mapping, future), as_of=NOW)
