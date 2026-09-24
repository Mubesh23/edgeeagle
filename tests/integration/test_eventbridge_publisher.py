"""Broker acceptance only: no queue, consumer, IAM policy, or production resource."""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import boto3
import pytest
from botocore.config import Config
from botocore.exceptions import ClientError
from mypy_boto3_events import EventBridgeClient
from sqlalchemy import Engine

from edgeeagle_ingestion.delivery import DeliveryClaim, DeliveryStatus, OutboxDeliveryRepository
from edgeeagle_ingestion.dispatch import DispatchResult, EventPublisher, dispatch_one
from edgeeagle_persistence.delivery import PostgresOutboxDeliveryRepository
from edgeeagle_persistence.eventbridge import EventBridgePublisher
from edgeeagle_persistence.events import PostgresEventAcceptanceRepository
from tests.integration.clocks import database_clock
from tests.integration.test_event_acceptance import seed
from tests.integration.test_outbox_delivery import enqueue, expire
from tests.integration.test_repositories import repository_engine as repository_engine


@pytest.fixture
def event_bus() -> Iterator[tuple[EventBridgeClient, str]]:
    port = int(os.environ.get("EDGEEAGLE_FLOCI_PORT", "4566"))
    client = boto3.client(
        "events",
        endpoint_url=f"http://127.0.0.1:{port}",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        aws_session_token="test",
        config=Config(
            connect_timeout=2,
            read_timeout=3,
            retries={"mode": "standard", "total_max_attempts": 1},
            proxies={},
        ),
    )
    name = f"edgeeagle-publisher-test-{uuid4().hex}"
    try:
        arn = client.create_event_bus(Name=name)["EventBusArn"]
        try:
            yield client, arn
        finally:
            client.delete_event_bus(Name=name)
    finally:
        client.close()


@pytest.mark.parametrize("crash", [False, True])
def test_eventbridge_dispatch_and_recovery(
    repository_engine: Engine,
    event_bus: tuple[EventBridgeClient, str],
    crash: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host_clock = Mock(wraps=datetime)
    host_clock.now.return_value = datetime(2000, 1, 1, tzinfo=UTC)
    monkeypatch.setattr("edgeeagle_persistence.eventbridge.datetime", host_clock)
    client, arn = event_bus
    with repository_engine.begin() as connection:
        seed(connection)
        message = enqueue(connection)

    @contextmanager
    def transactions() -> Iterator[OutboxDeliveryRepository]:
        with repository_engine.begin() as connection:
            yield PostgresOutboxDeliveryRepository(connection)

    real_publisher: EventPublisher = EventBridgePublisher(
        client, arn, clock=database_clock(repository_engine)
    )
    accepted: list[DeliveryClaim] = []

    class Publisher:
        def publish(self, claim: DeliveryClaim) -> None:
            real_publisher.publish(claim)
            accepted.append(claim)
            if crash:
                raise RuntimeError("crash after broker acceptance")

    def run() -> DispatchResult:
        return dispatch_one(
            transactions,
            Publisher(),
            lease_for=timedelta(minutes=1),
            retry_after=timedelta(seconds=10),
        )

    if crash:
        with pytest.raises(RuntimeError, match="crash after broker"):
            run()
        with repository_engine.begin() as connection:
            state = PostgresOutboxDeliveryRepository(connection).get(message.event_id)
            assert state is not None and state.status is DeliveryStatus.LEASED
            expire(connection, message.event_id)
        crash = False

    assert run() is DispatchResult.PUBLISHED
    assert run() is DispatchResult.IDLE
    host_clock.now.assert_not_called()
    assert [claim.attempt for claim in accepted] == list(range(1, len(accepted) + 1))
    assert all(claim.notification == message for claim in accepted)
    with repository_engine.begin() as connection:
        state = PostgresOutboxDeliveryRepository(connection).get(message.event_id)
        assert state is not None and state.status is DeliveryStatus.PUBLISHED
        assert state.attempts == len(accepted)
        original = PostgresEventAcceptanceRepository(connection).get_notification(
            message.canonical_event_id
        )
        assert original == message
        assert original.to_envelope()["published_at"] is None


def test_eventbridge_missing_bus_does_not_acknowledge(
    repository_engine: Engine,
    event_bus: tuple[EventBridgeClient, str],
) -> None:
    client, arn = event_bus
    with repository_engine.begin() as connection:
        seed(connection)
        message = enqueue(connection)

    @contextmanager
    def transactions() -> Iterator[OutboxDeliveryRepository]:
        with repository_engine.begin() as connection:
            yield PostgresOutboxDeliveryRepository(connection)

    with pytest.raises(ClientError) as error:
        dispatch_one(
            transactions,
            EventBridgePublisher(client, arn + "-missing", clock=database_clock(repository_engine)),
            lease_for=timedelta(minutes=1),
            retry_after=timedelta(seconds=10),
        )
    assert error.value.response["Error"]["Code"] == "ResourceNotFoundException"
    with repository_engine.begin() as connection:
        state = PostgresOutboxDeliveryRepository(connection).get(message.event_id)
        assert state is not None and state.status is DeliveryStatus.LEASED
        assert state.acknowledged_at is None
