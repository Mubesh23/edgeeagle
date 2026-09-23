import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from edgeeagle_ingestion.notifications import EventAccepted
from edgeeagle_persistence._event_snapshot import acceptance_key
from tests.unit.test_event_acceptance import candidate


def notification() -> EventAccepted:
    return EventAccepted.for_candidate(
        candidate(),
        event_id="notification-1",
        occurred_at=datetime(2026, 9, 23, tzinfo=UTC),
        correlation_id="fixture-workflow-1",
        causation_id="fixture-command-1",
    )


def test_notification_contract_and_round_trip() -> None:
    value = notification()
    schema = json.loads(
        (Path(__file__).parents[2] / "contracts/events/event-accepted.v1.json").read_text()
    )
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    envelope = value.to_envelope()
    validator.validate(envelope)
    assert envelope["published_at"] is None
    assert envelope["event_id"] == "notification-1"
    assert value.acceptance_key == acceptance_key(candidate())
    assert EventAccepted.from_envelope(envelope) == value
    published = value.to_envelope(published_at=value.occurred_at + timedelta(seconds=1))
    validator.validate(published)
    with pytest.raises(ValueError, match="pending"):
        EventAccepted.from_envelope(published)
    assert value.to_envelope()["published_at"] is None
    assert (
        replace(
            value, occurred_at=value.occurred_at.astimezone(timezone(timedelta(hours=5)))
        ).to_envelope()
        == envelope
    )


@pytest.mark.parametrize(
    "change",
    [
        {"event_id": ""},
        {"correlation_id": " padded"},
        {"causation_id": 3},
        {"occurred_at": datetime(2026, 9, 23)},
        {"acceptance_key": "bad"},
        {"canonical_event_id": "not-typed"},
    ],
)
def test_notification_invalid_values(change: dict[str, Any]) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(notification(), **change)


def test_notification_timestamp_guards() -> None:
    value = notification()
    with pytest.raises(ValueError):
        value.to_envelope(published_at=value.occurred_at - timedelta(seconds=1))
    with pytest.raises(ValueError):
        value.to_envelope(published_at=datetime(2026, 9, 23))
    with pytest.raises(ValueError):
        EventAccepted.for_candidate(
            candidate(),
            event_id="n",
            occurred_at=datetime(2000, 1, 1, tzinfo=UTC),
            correlation_id="c",
            causation_id="a",
        )


@pytest.mark.parametrize(
    "change",
    [
        {"version": True},
        {"version": 2},
        {"event_type": "Other"},
        {"payload": {}},
        {"extra": "field"},
        {"occurred_at": "invalid"},
    ],
)
def test_notification_rejects_bad_stored_envelope(change: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        EventAccepted.from_envelope(notification().to_envelope() | change)
