from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import Mock

import pytest

from edgeeagle_ingestion.delivery import DeliveryClaim, DeliveryLeaseLost, OutboxDeliveryRepository
from edgeeagle_ingestion.dispatch import DispatchResult, RetryablePublicationError, dispatch_one
from tests.unit.test_event_notifications import notification


class Transactions:
    def __init__(self) -> None:
        value = notification()
        self.claim = DeliveryClaim(
            notification=value,
            attempt=1,
            claimed_at=value.occurred_at,
            lease_expires_at=value.occurred_at + timedelta(minutes=1),
        )
        self.repository = Mock(spec=OutboxDeliveryRepository)
        self.repository.claim.return_value = self.claim
        self.active = False
        self.commits = 0
        self.fail_commit: int | None = None

    @contextmanager
    def __call__(self) -> Iterator[OutboxDeliveryRepository]:
        assert not self.active
        self.active = True
        try:
            yield self.repository
            if self.fail_commit == self.commits + 1:
                raise RuntimeError("commit failed")
            self.commits += 1
        finally:
            self.active = False


def run(transactions: Transactions, publisher: Mock) -> DispatchResult:
    return dispatch_one(
        transactions,
        publisher,
        lease_for=timedelta(minutes=1),
        retry_after=timedelta(seconds=10),
    )


def test_send_after_claim_commit_and_ack_in_new_transaction() -> None:
    transactions = Transactions()
    publisher = Mock()

    def publish(claim: DeliveryClaim) -> None:
        assert not transactions.active
        assert transactions.commits == 1
        assert claim == transactions.claim

    publisher.publish.side_effect = publish
    assert run(transactions, publisher) is DispatchResult.PUBLISHED
    assert transactions.commits == 2
    transactions.repository.acknowledge.assert_called_once_with(transactions.claim)
    transactions.repository.retry.assert_not_called()


def test_idle_does_not_publish_or_open_completion_transaction() -> None:
    transactions = Transactions()
    transactions.repository.claim.return_value = None
    publisher = Mock()
    assert run(transactions, publisher) is DispatchResult.IDLE
    assert transactions.commits == 1
    publisher.publish.assert_not_called()


def test_retryable_send_failure_schedules_retry_without_ack() -> None:
    transactions = Transactions()
    publisher = Mock()
    publisher.publish.side_effect = RetryablePublicationError("ambiguous acceptance")
    assert run(transactions, publisher) is DispatchResult.RETRY_SCHEDULED
    assert transactions.commits == 2
    transactions.repository.retry.assert_called_once_with(
        transactions.claim, retry_after=timedelta(seconds=10)
    )
    transactions.repository.acknowledge.assert_not_called()


@pytest.mark.parametrize("error", [ValueError("configuration"), KeyboardInterrupt()])
def test_unclassified_errors_and_interrupts_leave_claim_for_recovery(error: BaseException) -> None:
    transactions = Transactions()
    publisher = Mock()
    publisher.publish.side_effect = error
    with pytest.raises(type(error)):
        run(transactions, publisher)
    assert transactions.commits == 1
    transactions.repository.retry.assert_not_called()
    transactions.repository.acknowledge.assert_not_called()


@pytest.mark.parametrize("stage", [1, 2])
def test_commit_failure_propagates_without_resending(stage: int) -> None:
    transactions = Transactions()
    transactions.fail_commit = stage
    publisher = Mock()
    with pytest.raises(RuntimeError, match="commit failed"):
        run(transactions, publisher)
    assert publisher.publish.call_count == stage - 1
    transactions.repository.retry.assert_not_called()


def test_retry_commit_failure_does_not_report_scheduled_or_acknowledge() -> None:
    transactions = Transactions()
    transactions.fail_commit = 2
    publisher = Mock()
    publisher.publish.side_effect = RetryablePublicationError()
    with pytest.raises(RuntimeError, match="commit failed"):
        run(transactions, publisher)
    assert transactions.commits == 1
    assert publisher.publish.call_count == 1
    transactions.repository.acknowledge.assert_not_called()


def test_claim_failure_never_sends() -> None:
    transactions = Transactions()
    transactions.repository.claim.side_effect = ValueError("invalid stored envelope")
    publisher = Mock()
    with pytest.raises(ValueError, match="invalid stored envelope"):
        run(transactions, publisher)
    assert transactions.commits == 0
    publisher.publish.assert_not_called()


@pytest.mark.parametrize("retry", [False, True])
def test_lost_lease_propagates_without_overwriting_new_owner(retry: bool) -> None:
    transactions = Transactions()
    publisher = Mock()
    transactions.repository.acknowledge.side_effect = DeliveryLeaseLost()
    transactions.repository.retry.side_effect = DeliveryLeaseLost()
    if retry:
        publisher.publish.side_effect = RetryablePublicationError()
    with pytest.raises(DeliveryLeaseLost):
        run(transactions, publisher)
    assert transactions.commits == 1
    assert publisher.publish.call_count == 1


@pytest.mark.parametrize(
    "lease,retry",
    [
        (timedelta(0), timedelta(seconds=1)),
        (timedelta(hours=2), timedelta(seconds=1)),
        (timedelta(seconds=1), timedelta(0)),
        (timedelta(seconds=1), timedelta(days=2)),
    ],
)
def test_invalid_policy_fails_before_claim(lease: timedelta, retry: timedelta) -> None:
    transactions = Transactions()
    with pytest.raises(ValueError):
        dispatch_one(transactions, Mock(), lease_for=lease, retry_after=retry)
    transactions.repository.claim.assert_not_called()
