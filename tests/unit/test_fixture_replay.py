"""Read-only reproduction from trusted receipts, never current mapping reads."""

import json
from dataclasses import replace
from datetime import timedelta, timezone
from typing import Any
from unittest.mock import Mock, call

import pytest

from edgeeagle_domain.raw import RawPayloadIntegrityError
from edgeeagle_domain.sports import EventId
from edgeeagle_ingestion.events import EventCandidate
from edgeeagle_ingestion.identity import acceptance_key
from edgeeagle_ingestion.synthetic_events import replay_mapped_fixture_events
from edgeeagle_persistence._event_snapshot import decode, encode
from tests.unit.test_event_normalization import fixture_payload
from tests.unit.test_mapped_receipts import mapped_candidate


def retained() -> EventCandidate:
    return decode(
        json.loads(
            encode(replace(mapped_candidate(), normalizer_version="synthetic-event-mappings-v1"))
        )
    )


def test_replay_decoded_receipt_without_mapping_reads_or_writes() -> None:
    value, store = retained(), Mock()
    store.get.return_value = fixture_payload().body
    result = replay_mapped_fixture_events(store, value.raw, (value,))
    assert result == (value,)
    assert acceptance_key(result[0]) == acceptance_key(value)
    assert result[0].raw.capture.available_at is None
    assert store.mock_calls == [call.get(value.raw)]


def test_entry_order_and_equivalent_timestamp_offsets_are_not_drift() -> None:
    value, store = retained(), Mock()
    store.get.return_value = fixture_payload().body
    equivalent = replace(
        value,
        entries=tuple(reversed(value.entries)),
        event=replace(
            value.event,
            starts_at=value.event.starts_at.astimezone(timezone(timedelta(hours=-5))),
        ),
    )
    assert replay_mapped_fixture_events(store, value.raw, (equivalent,)) == (value,)


@pytest.mark.parametrize(
    "field", ["parser_version", "normalizer_version", "mapping_evidence", "raw"]
)
def test_unsupported_or_mixed_receipts_fail_before_storage_read(field: str) -> None:
    value, store = retained(), Mock()
    changes: dict[str, Any] = {
        "parser_version": "future-parser",
        "normalizer_version": "future-normalizer",
        "mapping_evidence": None,
        "raw": replace(value.raw, capture=replace(value.raw.capture, resource="other")),
    }
    with pytest.raises(ValueError):
        replay_mapped_fixture_events(store, value.raw, (replace(value, **{field: changes[field]}),))
    assert store.mock_calls == []


@pytest.mark.parametrize("field", ["starts_at", "venue_location"])
def test_full_event_drift_is_rejected_even_with_same_lineage_digest(field: str) -> None:
    value, store = retained(), Mock()
    store.get.return_value = fixture_payload().body
    event = (
        replace(value.event, starts_at=value.event.starts_at + timedelta(hours=1))
        if field == "starts_at"
        else replace(value.event, venue_location="Other")
    )
    changed = replace(value, event=event)
    assert acceptance_key(changed) == acceptance_key(value)
    with pytest.raises(ValueError, match="does not reproduce"):
        replay_mapped_fixture_events(store, value.raw, (changed,))


@pytest.mark.parametrize("failure", ["missing", "corrupt", "same-size", "malformed", "labels"])
def test_raw_failures_and_guard_mismatch(failure: str) -> None:
    raw, value, store = fixture_payload(), retained(), Mock()
    body: bytes | None = raw.body
    if failure == "missing":
        body = None
    elif failure == "corrupt":
        body = b"[]"
    elif failure == "same-size":
        body = b" " * len(raw.body)
    elif failure == "malformed":
        raw = replace(raw, body=b"not JSON")
        body = raw.body
        value = replace(value, raw=raw.reference())
    else:
        assert value.mapping_evidence is not None
        value = replace(value, mapping_evidence=replace(value.mapping_evidence, home_label="Other"))
    store.get.return_value = body
    with pytest.raises((ValueError, FileNotFoundError, RawPayloadIntegrityError)):
        replay_mapped_fixture_events(store, value.raw, (value,))
    store.put.assert_not_called()


def test_complete_batch_coverage_uniqueness_and_raw_order() -> None:
    raw, value, store = fixture_payload(), retained(), Mock()
    rows = json.loads(raw.body)
    rows.append(dict(rows[0], id="second-event"))
    raw = replace(raw, body=json.dumps(rows).encode())
    value = replace(value, raw=raw.reference())
    second = replace(
        value,
        provider_key=replace(value.provider_key, provider_entity_id="second-event"),
        event=replace(value.event, event_id=EventId("e2")),
        entries=tuple(replace(entry, event_id=EventId("e2")) for entry in value.entries),
    )
    store.get.return_value = raw.body
    assert replay_mapped_fixture_events(store, value.raw, (second, value)) == (value, second)
    collapsed = replace(second, event=value.event, entries=value.entries)
    for batch in ((), (value,), (value, value), (value, second, second), (value, collapsed)):
        with pytest.raises(ValueError, match="cover each event"):
            replay_mapped_fixture_events(store, value.raw, batch)
    # A bad later event must fail the entire replay, not return a verified prefix.
    drift = replace(second, event=replace(second.event, venue_location="Other"))
    with pytest.raises(ValueError, match="does not reproduce"):
        replay_mapped_fixture_events(store, value.raw, (value, drift))


def test_empty_capture_is_still_read_and_verified() -> None:
    raw, store = replace(fixture_payload(), body=b"[]"), Mock()
    store.get.return_value = raw.body
    assert replay_mapped_fixture_events(store, raw.reference(), ()) == ()
    store.get.assert_called_once_with(raw.reference())


@pytest.mark.parametrize(
    "reference,batch", [(None, ()), (retained().raw, []), (retained().raw, (None,))]
)
def test_invalid_input_types(reference: Any, batch: Any) -> None:
    store = Mock()
    with pytest.raises(TypeError):
        replay_mapped_fixture_events(store, reference, batch)
    assert store.mock_calls == []
