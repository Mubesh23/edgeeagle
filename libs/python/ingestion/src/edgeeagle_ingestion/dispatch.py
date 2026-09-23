"""One bounded relay attempt; transport and transaction ownership are injected."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import timedelta
from enum import Enum
from typing import Protocol

from edgeeagle_ingestion.delivery import (
    DeliveryClaim,
    OutboxDeliveryRepository,
    validate_duration,
)


class RetryablePublicationError(Exception):
    """Transport rejected transiently or acceptance is unknown; replay is safe."""


class EventPublisher(Protocol):
    def publish(self, claim: DeliveryClaim) -> None:
        """Return only after broker acceptance; preserve notification identity.

        Implementations must bound transport retries/timeouts within the lease.
        Raise RetryablePublicationError for transient or ambiguous acceptance.
        Configuration, malformed payload, and unexpected errors propagate.
        """
        ...


DeliveryTransactions = Callable[[], AbstractContextManager[OutboxDeliveryRepository]]


class DispatchResult(Enum):
    IDLE = "IDLE"
    PUBLISHED = "PUBLISHED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"


def dispatch_one(
    transactions: DeliveryTransactions,
    publisher: EventPublisher,
    *,
    lease_for: timedelta,
    retry_after: timedelta,
) -> DispatchResult:
    """Claim, commit, send, then complete in a fresh transaction.

    Each context must commit on normal exit, roll back on error, close its
    connection, and never suppress exceptions. It must not join an outer
    transaction. No broker call is made until the claim context exits normally.
    Errors in either transaction propagate; never resend within this invocation.
    Recovery after a send/ack failure may duplicate the same notification ID.
    """
    validate_duration(lease_for, maximum=timedelta(hours=1))
    validate_duration(retry_after, maximum=timedelta(days=1))
    with transactions() as repository:
        claim = repository.claim(lease_for=lease_for)
    if claim is None:
        return DispatchResult.IDLE

    try:
        publisher.publish(claim)
    except RetryablePublicationError:
        with transactions() as repository:
            repository.retry(claim, retry_after=retry_after)
        return DispatchResult.RETRY_SCHEDULED

    with transactions() as repository:
        repository.acknowledge(claim)
    return DispatchResult.PUBLISHED
