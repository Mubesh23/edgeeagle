from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import Mock

import pytest

from edgeeagle_ingestion.consumer import (
    ConsumptionResult,
    EventAcceptedHandler,
    NotificationDelivery,
    consume_one,
)
from tests.unit.test_event_notifications import notification


@pytest.mark.parametrize("created", [True, False])
def test_consumer_commits_before_deleting(created: bool) -> None:
    queue = Mock()
    delivery = NotificationDelivery(notification=notification(), receipt_handle="latest-handle")
    queue.receive.return_value = delivery
    handler = Mock(spec=EventAcceptedHandler)
    handler.handle.return_value = created
    committed = False

    @contextmanager
    def transaction() -> Iterator[EventAcceptedHandler]:
        nonlocal committed
        yield handler
        committed = True

    def acknowledge(value: NotificationDelivery) -> None:
        assert committed
        assert value == delivery

    queue.acknowledge.side_effect = acknowledge
    assert consume_one(queue, transaction) is (
        ConsumptionResult.PROCESSED if created else ConsumptionResult.DUPLICATE
    )
    handler.handle.assert_called_once_with(delivery.notification)
    queue.acknowledge.assert_called_once_with(delivery)


@pytest.mark.parametrize("stage", ["receive", "handle", "commit", "delete"])
def test_consumer_failures_propagate_without_early_delete(stage: str) -> None:
    queue = Mock()
    queue.receive.return_value = NotificationDelivery(
        notification=notification(),
        receipt_handle="handle",
    )
    handler = Mock(spec=EventAcceptedHandler)
    handler.handle.return_value = True
    committed = False

    @contextmanager
    def transaction() -> Iterator[EventAcceptedHandler]:
        nonlocal committed
        yield handler
        if stage == "commit":
            raise RuntimeError("commit")
        committed = True

    if stage == "receive":
        queue.receive.side_effect = RuntimeError(stage)
    if stage == "handle":
        handler.handle.side_effect = RuntimeError(stage)
    if stage == "delete":
        queue.acknowledge.side_effect = RuntimeError(stage)
    with pytest.raises(RuntimeError, match=stage):
        consume_one(queue, transaction)
    assert queue.acknowledge.call_count == (1 if stage == "delete" else 0)
    assert committed is (stage == "delete")


def test_consumer_idle_never_opens_transaction() -> None:
    queue = Mock()
    queue.receive.return_value = None
    transaction = Mock()
    assert consume_one(queue, transaction) is ConsumptionResult.IDLE
    transaction.assert_not_called()
    queue.acknowledge.assert_not_called()
