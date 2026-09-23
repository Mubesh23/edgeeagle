"""Acceptance boundary and private receipt codec; no network."""

import json
from dataclasses import replace
from datetime import timedelta, timezone
from typing import Any
from unittest.mock import Mock

import pytest

from edgeeagle_domain.provenance import DataSourceId
from edgeeagle_domain.sports import EventId
from edgeeagle_ingestion.events import EventCandidate
from edgeeagle_ingestion.synthetic_events import normalize_fixture_events
from edgeeagle_persistence._event_snapshot import acceptance_key, canonical, decode, encode
from tests.unit.test_event_normalization import binding, fixture_payload


def candidate() -> EventCandidate:
    payload = fixture_payload()
    store = Mock()
    store.get.return_value = payload.body
    return normalize_fixture_events(store, payload.reference(), (binding(),))[0]


def test_receipt_round_trip_and_identity() -> None:
    original = candidate()
    offset = replace(
        original,
        event=replace(
            original.event,
            starts_at=original.event.starts_at.astimezone(timezone(timedelta(hours=-5))),
        ),
        entries=tuple(reversed(original.entries)),
    )
    assert encode(offset) == encode(original)
    assert acceptance_key(offset) == acceptance_key(original)
    assert decode(json.loads(encode(original))) == canonical(original)
    assert decode(json.loads(encode(original))).raw.capture.available_at is None
    assert acceptance_key(replace(original, parser_version="v2")) != acceptance_key(original)
    assert acceptance_key(replace(original, event=replace(original.event, status="FINAL"))) == (
        acceptance_key(original)
    )


@pytest.mark.parametrize(
    "change",
    [
        {"entries": ()},
        {"entries": []},
        {"event": "event"},
        {"raw": "raw"},
        {"provider_key": "key"},
        {"parser_version": " padded"},
        {"normalizer_version": ""},
        {"context_version": 1},
    ],
)
def test_candidate_rejects_invalid_values(change: dict[str, Any]) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(candidate(), **change)


def test_candidate_checks_source_and_entries() -> None:
    original = candidate()
    invalid = [
        {"provider_key": replace(original.provider_key, data_source_id=DataSourceId("other"))},
        {"provider_key": replace(original.provider_key, provider_entity_type="team")},
        {"entries": (original.entries[0], original.entries[0])},
        {"entries": (replace(original.entries[0], event_id=EventId("other")),)},
        {"entries": ("invalid",)},
    ]
    for change in invalid:
        with pytest.raises((TypeError, ValueError)):
            replace(original, **change)  # type: ignore[arg-type]


@pytest.mark.parametrize("snapshot", [None, [], {}, {"format": 2}, {"format": True}])
def test_receipt_rejects_unknown_or_missing_format(snapshot: Any) -> None:
    with pytest.raises(ValueError, match="Invalid event normalization receipt"):
        decode(snapshot)


@pytest.mark.parametrize(
    "path,value",
    [
        (("extra",), 1),
        (("candidate", "extra"), 1),
        (("candidate", "event", "event_id", "extra"), 1),
        (("candidate", "event", "starts_at"), "2026-10-01T18:00:00"),
        (("candidate", "raw", "size_bytes"), True),
        (("candidate", "raw", "capture", "available_at"), "2099-01-01T00:00:00+00:00"),
        (("candidate", "provider_key", "data_source_id", "value"), "different"),
    ],
)
def test_receipt_rejects_corruption(path: tuple[str, ...], value: Any) -> None:
    snapshot = json.loads(encode(candidate()))
    target = snapshot
    for component in path[:-1]:
        target = target[component]
    target[path[-1]] = value
    with pytest.raises(ValueError, match="Invalid event normalization receipt"):
        decode(snapshot)
