"""Transport-neutral outbox coordination contracts; no database or clock access."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Protocol

from edgeeagle_domain._validation import aware_datetime, instance, text
from edgeeagle_ingestion.notifications import EventAccepted


def validate_duration(value: timedelta, *, maximum: timedelta) -> None:
    instance(value, timedelta, "duration")
    if not timedelta(0) < value <= maximum:
        raise ValueError("duration must be positive and within its configured bound")


class DeliveryStatus(Enum):
    PENDING = "PENDING"
    LEASED = "LEASED"
    PUBLISHED = "PUBLISHED"


class DeliveryLeaseLost(Exception):
    """Claim expired, was superseded, or is no longer leased."""


@dataclass(frozen=True, kw_only=True)
class DeliveryState:
    notification_id: str
    status: DeliveryStatus
    attempts: int
    ready_at: datetime
    claimed_at: datetime | None
    lease_expires_at: datetime | None
    acknowledged_at: datetime | None

    def __post_init__(self) -> None:
        text(self.notification_id, "notification_id")
        instance(self.status, DeliveryStatus, "status")
        if type(self.attempts) is not int or self.attempts < 0:
            raise ValueError("attempts must be a nonnegative integer")
        aware_datetime(self.ready_at, "ready_at")
        for name in ("ready_at", "claimed_at", "lease_expires_at", "acknowledged_at"):
            value = getattr(self, name)
            if value is not None:
                aware_datetime(value, name)
                object.__setattr__(self, name, value.astimezone(UTC))
        if self.status is DeliveryStatus.PENDING:
            if any(
                value is not None
                for value in (self.claimed_at, self.lease_expires_at, self.acknowledged_at)
            ):
                raise ValueError("pending delivery cannot have a lease or acknowledgement")
        else:
            if self.attempts == 0 or self.claimed_at is None or self.lease_expires_at is None:
                raise ValueError("leased/published delivery requires a claim")
            if self.lease_expires_at <= self.claimed_at:
                raise ValueError("lease expiry must follow claim time")
            if self.status is DeliveryStatus.LEASED:
                if self.acknowledged_at is not None:
                    raise ValueError("leased delivery cannot be acknowledged")
            elif (
                self.acknowledged_at is None
                or not self.claimed_at <= self.acknowledged_at < self.lease_expires_at
            ):
                raise ValueError("acknowledgement must occur during the lease")


@dataclass(frozen=True, kw_only=True)
class DeliveryClaim:
    notification: EventAccepted
    attempt: int
    claimed_at: datetime
    lease_expires_at: datetime

    def __post_init__(self) -> None:
        instance(self.notification, EventAccepted, "notification")
        if type(self.attempt) is not int or self.attempt < 1:
            raise ValueError("attempt must be a positive integer")
        aware_datetime(self.claimed_at, "claimed_at")
        aware_datetime(self.lease_expires_at, "lease_expires_at")
        if not self.notification.occurred_at <= self.claimed_at < self.lease_expires_at:
            raise ValueError("require occurrence <= claim < lease expiry")
        object.__setattr__(self, "claimed_at", self.claimed_at.astimezone(UTC))
        object.__setattr__(self, "lease_expires_at", self.lease_expires_at.astimezone(UTC))


class OutboxDeliveryRepository(Protocol):
    def claim(self, *, lease_for: timedelta) -> DeliveryClaim | None: ...

    def acknowledge(self, claim: DeliveryClaim) -> None: ...

    def retry(self, claim: DeliveryClaim, *, retry_after: timedelta) -> None: ...

    def get(self, notification_id: str) -> DeliveryState | None: ...
