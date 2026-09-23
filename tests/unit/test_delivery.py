from dataclasses import replace
from datetime import timedelta

import pytest

from edgeeagle_ingestion.delivery import (
    DeliveryClaim,
    DeliveryState,
    DeliveryStatus,
    validate_duration,
)
from tests.unit.test_event_notifications import notification


def test_delivery_claim_validation() -> None:
    message = notification()
    claim = DeliveryClaim(
        notification=message,
        attempt=1,
        claimed_at=message.occurred_at,
        lease_expires_at=message.occurred_at + timedelta(seconds=10),
    )
    assert claim.attempt == 1
    for attempt in (0, -1, True):
        with pytest.raises(ValueError):
            replace(claim, attempt=attempt)
    with pytest.raises(ValueError):
        replace(claim, lease_expires_at=claim.claimed_at)
    with pytest.raises(ValueError):
        replace(claim, claimed_at=message.occurred_at - timedelta(seconds=1))


def test_delivery_duration_bounds() -> None:
    validate_duration(timedelta(hours=1), maximum=timedelta(hours=1))
    for value in (timedelta(0), timedelta(seconds=-1), timedelta(hours=2)):
        with pytest.raises(ValueError):
            validate_duration(value, maximum=timedelta(hours=1))


def test_delivery_state_shapes() -> None:
    now = notification().occurred_at
    pending = DeliveryState(
        notification_id="n",
        status=DeliveryStatus.PENDING,
        attempts=0,
        ready_at=now,
        claimed_at=None,
        lease_expires_at=None,
        acknowledged_at=None,
    )
    with pytest.raises(ValueError):
        replace(pending, attempts=True)
    with pytest.raises(ValueError):
        replace(pending, claimed_at=now)
    with pytest.raises(ValueError):
        replace(pending, status=DeliveryStatus.LEASED)
    leased = replace(
        pending,
        status=DeliveryStatus.LEASED,
        attempts=1,
        claimed_at=now,
        lease_expires_at=now + timedelta(minutes=1),
    )
    with pytest.raises(ValueError):
        replace(leased, lease_expires_at=now)
    with pytest.raises(ValueError):
        replace(leased, acknowledged_at=now)
    with pytest.raises(ValueError):
        replace(leased, status=DeliveryStatus.PUBLISHED)
    published = replace(leased, status=DeliveryStatus.PUBLISHED, acknowledged_at=now)
    assert published.acknowledged_at == now
    with pytest.raises(ValueError):
        replace(published, acknowledged_at=now + timedelta(minutes=2))
