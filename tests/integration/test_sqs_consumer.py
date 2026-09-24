import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import timedelta

import pytest
from sqlalchemy import Engine, text

from edgeeagle_ingestion.consumer import (
    ConsumptionResult,
    EventAcceptedHandler,
    NotificationDelivery,
    consume_one,
)
from edgeeagle_ingestion.delivery import DeliveryClaim
from edgeeagle_persistence.consumer import PostgresEventAcceptedHandler
from edgeeagle_persistence.delivery import PostgresOutboxDeliveryRepository
from edgeeagle_persistence.eventbridge import EventBridgePublisher
from tests.integration.clocks import database_clock
from tests.integration.sqs_routing import Routing
from tests.integration.sqs_routing import event_bus as event_bus
from tests.integration.sqs_routing import routing as routing
from tests.integration.test_event_acceptance import seed
from tests.integration.test_outbox_delivery import enqueue
from tests.integration.test_repositories import repository_engine as repository_engine


def publish(engine: Engine, routing: Routing, *, duplicate: bool = False) -> DeliveryClaim:
    with engine.begin() as connection:
        seed(connection)
        enqueue(connection)
        claim = PostgresOutboxDeliveryRepository(connection).claim(lease_for=timedelta(minutes=1))
        assert claim is not None
    adapter = EventBridgePublisher(routing.events, routing.bus, clock=database_clock(engine))
    adapter.publish(claim)
    if duplicate:
        adapter.publish(claim)  # Simulate a lost publication acknowledgement.
    with engine.begin() as connection:
        PostgresOutboxDeliveryRepository(connection).acknowledge(claim)
    return claim


def wait_delivery(routing: Routing) -> NotificationDelivery:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        value = routing.queue(routing.queue_url).receive()
        if value is not None:
            return value
        time.sleep(0.05)
    raise AssertionError("EventBridge did not route to the source queue")


def test_sqs_routing_and_duplicate_effect(repository_engine: Engine, routing: Routing) -> None:
    claim = publish(repository_engine, routing, duplicate=True)
    results = []
    for _ in range(2):
        delivery = wait_delivery(routing)
        assert delivery.notification == claim.notification
        with repository_engine.begin() as connection:
            results.append(PostgresEventAcceptedHandler(connection).handle(delivery.notification))
        routing.queue(routing.queue_url).acknowledge(delivery)
    assert results == [True, False]
    with repository_engine.begin() as connection:
        assert connection.scalar(text("SELECT count(*) FROM event_acceptance_consumptions")) == 1
    for url in (routing.queue_url, routing.consumer_dlq_url, routing.delivery_dlq_url):
        assert not routing.queue(url).depth().has_messages


@pytest.mark.parametrize("stage", ["commit", "delete"])
def test_sqs_redelivery_after_commit_or_delete_failure(
    repository_engine: Engine,
    routing: Routing,
    stage: str,
) -> None:
    publish(repository_engine, routing)
    delivery = wait_delivery(routing)
    queue = routing.queue(routing.queue_url)
    fail = True

    class Queue:
        def receive(self) -> NotificationDelivery | None:
            return delivery if fail else queue.receive()

        def acknowledge(self, value: NotificationDelivery) -> None:
            if fail and stage == "delete":
                raise RuntimeError("injected delete failure")
            queue.acknowledge(value)

    @contextmanager
    def transactions() -> Iterator[EventAcceptedHandler]:
        with repository_engine.begin() as connection:
            yield PostgresEventAcceptedHandler(connection)
            if fail and stage == "commit":
                raise RuntimeError("injected commit failure")

    with pytest.raises(RuntimeError, match="injected"):
        consume_one(Queue(), transactions)
    routing.sqs.change_message_visibility(
        QueueUrl=routing.queue_url, ReceiptHandle=delivery.receipt_handle, VisibilityTimeout=0
    )
    fail = False
    assert consume_one(Queue(), transactions) is (
        ConsumptionResult.PROCESSED if stage == "commit" else ConsumptionResult.DUPLICATE
    )
    with repository_engine.begin() as connection:
        assert connection.scalar(text("SELECT count(*) FROM event_acceptance_consumptions")) == 1
    assert not queue.depth().has_messages


def test_sqs_poison_redrive_and_dlq_monitoring(repository_engine: Engine, routing: Routing) -> None:
    poison = {"event_type": "EventAccepted", "version": 99}
    result = routing.events.put_events(
        Entries=[
            {
                "EventBusName": routing.bus,
                "Source": "edgeeagle.ingestion",
                "DetailType": "EventAccepted",
                "Detail": json.dumps(poison),
            }
        ]
    )
    assert result["FailedEntryCount"] == 0

    @contextmanager
    def transactions() -> Iterator[EventAcceptedHandler]:
        with repository_engine.begin() as connection:
            yield PostgresEventAcceptedHandler(connection)

    queue = routing.queue(routing.queue_url)
    dead = routing.queue(routing.consumer_dlq_url)
    rejected = 0
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and not dead.depth().has_messages:
        try:
            assert consume_one(queue, transactions) is ConsumptionResult.IDLE
        except ValueError:
            rejected += 1
        time.sleep(0.05)
    assert rejected == 2
    assert dead.depth().visible == 1
    assert not queue.depth().has_messages
    received = routing.sqs.receive_message(QueueUrl=routing.consumer_dlq_url, MaxNumberOfMessages=1)
    assert json.loads(received["Messages"][0]["Body"])["detail"] == poison
    with repository_engine.begin() as connection:
        assert connection.scalar(text("SELECT count(*) FROM event_acceptance_consumptions")) == 0
    assert not routing.queue(routing.delivery_dlq_url).depth().has_messages


class MissingDeliveryDlqMessage(AssertionError):
    """The pinned emulator logs target failures without forwarding to the DLQ."""


@pytest.mark.xfail(
    strict=True,
    raises=MissingDeliveryDlqMessage,
    reason="Floci 2.1.0 EventBridgeInvoker lacks delivery-DLQ forwarding; see ADR-023",
)
def test_eventbridge_target_failure_reaches_delivery_dlq(routing: Routing) -> None:
    targets = routing.events.put_targets(
        Rule=routing.rule,
        EventBusName=routing.bus,
        Targets=[
            {
                "Id": "consumer",
                "Arn": routing.queue_arn + "-missing",
                "DeadLetterConfig": {"Arn": routing.delivery_dlq_arn},
                "RetryPolicy": {"MaximumRetryAttempts": 0, "MaximumEventAgeInSeconds": 60},
            }
        ],
    )
    assert targets["FailedEntryCount"] == 0
    result = routing.events.put_events(
        Entries=[
            {
                "EventBusName": routing.bus,
                "Source": "edgeeagle.ingestion",
                "DetailType": "EventAccepted",
                "Detail": '{"failure_probe":true}',
            }
        ]
    )
    assert result["FailedEntryCount"] == 0
    dead = routing.queue(routing.delivery_dlq_url)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and not dead.depth().has_messages:
        time.sleep(0.05)
    if dead.depth().visible == 0:
        raise MissingDeliveryDlqMessage("EventBridge target failure did not reach its DLQ")
    assert dead.depth().visible == 1
    received = routing.sqs.receive_message(QueueUrl=routing.delivery_dlq_url, MaxNumberOfMessages=1)
    assert json.loads(received["Messages"][0]["Body"])["detail"] == {"failure_probe": True}
