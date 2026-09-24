from dataclasses import FrozenInstanceError, replace
from datetime import UTC, timedelta, timezone
from typing import Any

import pytest

from edgeeagle_domain.sports import ParticipantId
from edgeeagle_ingestion.odds_api_parser import NativeOddsEvent
from edgeeagle_ingestion.odds_guards import OddsEventGuard, validate_odds_event_guard
from edgeeagle_ingestion.odds_references import ResolvedOddsReferences, resolve_odds_references
from tests.unit.test_fixture_references import NOW
from tests.unit.test_odds_references import setup_references


def guarded_event() -> tuple[OddsEventGuard, NativeOddsEvent, ResolvedOddsReferences]:
    refs = resolve_odds_references(*setup_references(), as_of=NOW)
    guard = OddsEventGuard(
        event_key=refs.revisions[1].key,
        home_id=refs.home.participant_id,
        away_id=refs.away.participant_id,
        home_label="Provider Home Label",
        away_label="Provider Away Label",
        starts_at=refs.event.starts_at,
    )
    native = NativeOddsEvent(
        guard.event_key.provider_entity_id,
        refs.revisions[0].key.provider_entity_id,
        guard.starts_at,
        guard.home_label,
        guard.away_label,
        (),
    )
    return guard, native, refs


def test_explicit_labels_need_not_equal_canonical_display_names() -> None:
    guard, native, refs = guarded_event()
    assert guard.home_label != refs.home.canonical_name
    validate_odds_event_guard(guard, native, refs, snapshot_at=NOW)
    with pytest.raises(FrozenInstanceError):
        guard.home_label = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "changes",
    [
        {"home_label": ""},
        {"home_label": " padded"},
        {"home_label": "x" * 257},
        {"home_label": "control\x00"},
        {"home_label": "surrogate\ud800"},
        {"home_label": "Draw"},
        {"away_label": "Provider Home Label"},
        {"starts_at": NOW.replace(tzinfo=None)},
        {"home_id": "untyped"},
        {"event_key": "untyped"},
    ],
)
def test_invalid_guard_is_rejected(changes: dict[str, Any]) -> None:
    guard, _, _ = guarded_event()
    with pytest.raises((ValueError, TypeError)):
        replace(guard, **changes)


def test_guard_requires_distinct_participants_and_event_key() -> None:
    guard, _, _ = guarded_event()
    with pytest.raises(ValueError):
        replace(guard, away_id=guard.home_id)
    with pytest.raises(ValueError):
        replace(guard, event_key=replace(guard.event_key, provider_entity_type="team"))


@pytest.mark.parametrize(
    "changes",
    [
        {"event_id": "different"},
        {"sport_key": "soccer_other"},
        {"home_team": "provider home label"},
        {"away_team": "Provider Home Label"},
        {"commence_time": NOW},
        {"commence_time": NOW.replace(tzinfo=None)},
    ],
)
def test_changed_native_context_fails_closed(changes: dict[str, Any]) -> None:
    guard, native, refs = guarded_event()
    with pytest.raises(ValueError):
        validate_odds_event_guard(guard, replace(native, **changes), refs, snapshot_at=NOW)


def test_wrong_guard_identity_or_canonical_context_is_rejected() -> None:
    guard, native, refs = guarded_event()
    for changed in (
        replace(guard, home_id=ParticipantId("other")),
        replace(guard, home_id=guard.away_id, away_id=guard.home_id),
        replace(guard, event_key=replace(guard.event_key, provider_entity_id="other")),
        replace(guard, starts_at=guard.starts_at + timedelta(seconds=1)),
    ):
        with pytest.raises(ValueError):
            validate_odds_event_guard(changed, native, refs, snapshot_at=NOW)
    changed_refs = replace(refs, event=replace(refs.event, starts_at=NOW))
    with pytest.raises(ValueError):
        validate_odds_event_guard(guard, native, changed_refs, snapshot_at=NOW)


def test_strictly_pre_match_and_aware_snapshot_required() -> None:
    guard, native, refs = guarded_event()
    for snapshot in (
        guard.starts_at,
        guard.starts_at + timedelta(seconds=1),
        NOW.replace(tzinfo=None),
    ):
        with pytest.raises(ValueError):
            validate_odds_event_guard(guard, native, refs, snapshot_at=snapshot)


def test_retained_guard_and_references_validate_without_repository_reads() -> None:
    guard, native, refs = guarded_event()
    # No repository or clock is passed: replay consumes only retained values.
    validate_odds_event_guard(guard, native, refs, snapshot_at=NOW)
    assert refs.as_of == NOW


def test_wrong_mapping_key_roles_fail_closed() -> None:
    guard, native, refs = guarded_event()
    wrong = replace(
        refs.revisions[0], key=replace(refs.revisions[0].key, provider_entity_type="event")
    )
    refs = replace(refs, revisions=(wrong, *refs.revisions[1:]))
    with pytest.raises(ValueError):
        validate_odds_event_guard(guard, native, refs, snapshot_at=NOW)


def test_equivalent_timezone_offsets_preserve_the_instant() -> None:
    guard, native, refs = guarded_event()
    offset = timezone(timedelta(hours=2))
    guard = replace(guard, starts_at=guard.starts_at.astimezone(offset))
    assert guard.starts_at.tzinfo is UTC
    native = replace(native, commence_time=native.commence_time.astimezone(offset))
    validate_odds_event_guard(guard, native, refs, snapshot_at=NOW.astimezone(offset))
