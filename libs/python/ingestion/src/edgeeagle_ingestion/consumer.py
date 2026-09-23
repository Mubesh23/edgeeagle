"""Bounded notification consumption; transport and transaction adapters stay outside."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from edgeeagle_domain._validation import instance, text
from edgeeagle_ingestion.notifications import EventAccepted


class EventConsumptionConflict(Exception):
    """Received notification does not match its immutable acceptance evidence."""


@dataclass(frozen=True, kw_only=True)
class NotificationDelivery:
    notification: EventAccepted
    receipt_handle: str

    def __post_init__(self) -> None:
        instance(self.notification, EventAccepted, "notification")
        text(self.receipt_handle, "receipt_handle")


class NotificationQueue(Protocol):
    def receive(self) -> NotificationDelivery | None: ...

    def acknowledge(self, delivery: NotificationDelivery) -> None: ...


class EventAcceptedHandler(Protocol):
    def handle(self, notification: EventAccepted) -> bool:
        """Verify and record once atomically; False for an identical duplicate."""
        ...


class ConsumptionResult(Enum):
    IDLE = "IDLE"
    PROCESSED = "PROCESSED"
    DUPLICATE = "DUPLICATE"


def consume_one(
    queue: NotificationQueue,
    transactions: Callable[[], AbstractContextManager[EventAcceptedHandler]],
) -> ConsumptionResult:
    """Commit before delete; errors leave the message to visibility/redrive policy.

    Contexts must commit on normal exit, roll back on error, never suppress errors,
    and not join an outer transaction. No receive or delete holds a DB transaction.
    This is one attempt, not a supervised poll loop or an exactly-once transport.
    """
    delivery = queue.receive()
    if delivery is None:
        return ConsumptionResult.IDLE
    with transactions() as handler:
        created = handler.handle(delivery.notification)
    queue.acknowledge(delivery)
    return ConsumptionResult.PROCESSED if created else ConsumptionResult.DUPLICATE
