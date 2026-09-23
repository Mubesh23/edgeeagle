import json
from collections.abc import Iterator
from dataclasses import replace
from datetime import timedelta
from typing import Any
from unittest.mock import Mock

import boto3
import pytest
from botocore.config import Config
from botocore.exceptions import ClientError, EndpointConnectionError, ReadTimeoutError
from botocore.stub import Stubber
from mypy_boto3_events import EventBridgeClient

from edgeeagle_ingestion.delivery import DeliveryClaim, DeliveryLeaseLost
from edgeeagle_ingestion.dispatch import RetryablePublicationError
from edgeeagle_persistence.eventbridge import EventBridgePublicationError, EventBridgePublisher
from tests.unit.test_event_notifications import notification

BUS = "arn:aws:events:us-east-1:000000000000:event-bus/edgeeagle-test"
SUCCESS = {
    "ResponseMetadata": {"HTTPStatusCode": 200},
    "FailedEntryCount": 0,
    "Entries": [{"EventId": "broker-id-not-domain-id"}],
}


@pytest.fixture
def client() -> Iterator[EventBridgeClient]:
    value = boto3.client(
        "events",
        region_name="us-east-1",
        endpoint_url="http://127.0.0.1:4566",
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
    try:
        yield value
    finally:
        value.close()


def claim() -> DeliveryClaim:
    value = notification()
    return DeliveryClaim(
        notification=value,
        attempt=1,
        claimed_at=value.occurred_at,
        lease_expires_at=value.occurred_at + timedelta(minutes=1),
    )


def publisher(client: EventBridgeClient) -> EventBridgePublisher:
    return EventBridgePublisher(client, BUS, clock=lambda: claim().claimed_at)


def describe(stubber: Stubber) -> None:
    stubber.add_response(
        "describe_event_bus",
        {
            "Arn": BUS,
            "Name": "edgeeagle-test",
            "ResponseMetadata": {"HTTPStatusCode": 200},
        },
        {"Name": BUS},
    )


def test_eventbridge_wire_format_and_immutable_identity(client: EventBridgeClient) -> None:
    value = claim()
    expected = {
        "Entries": [
            {
                "EventBusName": BUS,
                "Source": "edgeeagle.ingestion",
                "DetailType": "EventAccepted",
                "Time": value.notification.occurred_at,
                "Detail": json.dumps(
                    value.notification.to_envelope(published_at=value.claimed_at),
                    separators=(",", ":"),
                    ensure_ascii=False,
                ),
            }
        ]
    }
    with Stubber(client) as stubber:
        describe(stubber)
        stubber.add_response("put_events", SUCCESS, expected)
        publisher(client).publish(value)
        stubber.assert_no_pending_responses()
    assert value.notification.to_envelope()["published_at"] is None


@pytest.mark.parametrize(
    "code,retryable",
    [
        ("InternalFailure", True),
        ("ThrottlingException", True),
        ("AccessDeniedException", False),
        ("MalformedDetail", False),
        ("UnknownCode", False),
    ],
)
def test_eventbridge_entry_errors_not_http_success(
    client: EventBridgeClient,
    code: str,
    retryable: bool,
) -> None:
    with Stubber(client) as stubber:
        describe(stubber)
        stubber.add_response(
            "put_events",
            {
                "ResponseMetadata": {"HTTPStatusCode": 200},
                "FailedEntryCount": 1,
                "Entries": [{"ErrorCode": code, "ErrorMessage": "do not echo provider body"}],
            },
        )
        with pytest.raises(RetryablePublicationError if retryable else EventBridgePublicationError):
            publisher(client).publish(claim())
        stubber.assert_no_pending_responses()


@pytest.mark.parametrize("operation", ["describe_event_bus", "put_events"])
@pytest.mark.parametrize(
    "code,status,retryable",
    [
        ("InternalException", 500, True),
        ("ThrottlingException", 400, True),
        ("UnknownError", 503, True),
        ("UnknownError", 429, True),
        ("ResourceNotFoundException", 400, False),
        ("AccessDeniedException", 403, False),
    ],
)
def test_eventbridge_request_errors(
    client: EventBridgeClient,
    operation: str,
    code: str,
    status: int,
    retryable: bool,
) -> None:
    with Stubber(client) as stubber:
        if operation == "put_events":
            describe(stubber)
        stubber.add_client_error(operation, service_error_code=code, http_status_code=status)
        with pytest.raises(RetryablePublicationError if retryable else ClientError):
            publisher(client).publish(claim())
        stubber.assert_no_pending_responses()


@pytest.mark.parametrize(
    "response",
    [
        None,
        {},
        {**SUCCESS, "Entries": []},
        {**SUCCESS, "Entries": [{}, {}]},
        {**SUCCESS, "Entries": [{"EventId": ""}]},
        {**SUCCESS, "Entries": [{"EventId": " id "}]},
        {**SUCCESS, "Entries": [{"EventId": "id", "ErrorCode": "InternalFailure"}]},
        {**SUCCESS, "FailedEntryCount": True},
        {**SUCCESS, "FailedEntryCount": 1},
        {**SUCCESS, "ResponseMetadata": {"HTTPStatusCode": 503}},
        {**SUCCESS, "Entries": None},
        {**SUCCESS, "Entries": [None]},
    ],
)
def test_eventbridge_malformed_acceptance_is_ambiguous(
    client: EventBridgeClient,
    response: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Malformed wire data intentionally bypasses Stubber's SDK shape validator.
    monkeypatch.setattr(
        client,
        "describe_event_bus",
        Mock(
            return_value={
                "Arn": BUS,
                "ResponseMetadata": {"HTTPStatusCode": 200},
            }
        ),
    )
    monkeypatch.setattr(client, "put_events", Mock(return_value=response))
    with pytest.raises(RetryablePublicationError):
        publisher(client).publish(claim())


@pytest.mark.parametrize(
    "error",
    [
        ReadTimeoutError(endpoint_url="http://127.0.0.1"),
        EndpointConnectionError(endpoint_url="http://127.0.0.1"),
    ],
)
def test_eventbridge_connection_errors_are_retryable(
    client: EventBridgeClient,
    error: Exception,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(client, "describe_event_bus", Mock(side_effect=error))
    with pytest.raises(RetryablePublicationError):
        publisher(client).publish(claim())


def test_eventbridge_wrong_bus_never_puts(client: EventBridgeClient) -> None:
    with Stubber(client) as stubber:
        stubber.add_response(
            "describe_event_bus",
            {
                "Arn": BUS + "-other",
                "ResponseMetadata": {"HTTPStatusCode": 200},
            },
        )
        with pytest.raises(EventBridgePublicationError):
            publisher(client).publish(claim())


@pytest.mark.parametrize("offset", [-1, 50, 60, 61])
def test_eventbridge_lease_clock_guards_before_network(
    client: EventBridgeClient, offset: int
) -> None:
    value = claim()
    adapter = EventBridgePublisher(
        client, BUS, clock=lambda: value.claimed_at + timedelta(seconds=offset)
    )
    with Stubber(client), pytest.raises((ValueError, DeliveryLeaseLost)):
        adapter.publish(value)


def test_eventbridge_rechecks_lease_after_describe(client: EventBridgeClient) -> None:
    value = claim()
    times = iter([value.claimed_at, value.lease_expires_at - timedelta(seconds=5)])
    adapter = EventBridgePublisher(client, BUS, clock=lambda: next(times))
    with Stubber(client) as stubber:
        describe(stubber)
        with pytest.raises(DeliveryLeaseLost):
            adapter.publish(value)
        stubber.assert_no_pending_responses()


def test_eventbridge_stamps_delivery_copy_immediately_before_put(
    client: EventBridgeClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    value = claim()
    later = value.claimed_at + timedelta(seconds=2)
    times = iter([value.claimed_at, later])
    monkeypatch.setattr(
        client,
        "describe_event_bus",
        Mock(
            return_value={
                "Arn": BUS,
                "ResponseMetadata": {"HTTPStatusCode": 200},
            }
        ),
    )
    put = Mock(return_value=SUCCESS)
    monkeypatch.setattr(client, "put_events", put)
    EventBridgePublisher(client, BUS, clock=lambda: next(times)).publish(value)
    detail = json.loads(put.call_args.kwargs["Entries"][0]["Detail"])
    assert detail == value.notification.to_envelope(published_at=later)
    assert value.notification.to_envelope()["published_at"] is None


def test_eventbridge_requires_aware_clock(client: EventBridgeClient) -> None:
    with Stubber(client), pytest.raises(ValueError):
        EventBridgePublisher(
            client, BUS, clock=lambda: claim().claimed_at.replace(tzinfo=None)
        ).publish(claim())


def test_eventbridge_large_detail_rejected_before_network(client: EventBridgeClient) -> None:
    value = claim()
    value = replace(value, notification=replace(value.notification, correlation_id="é" * 40000))
    with Stubber(client), pytest.raises(ValueError, match="64 KiB"):
        publisher(client).publish(value)


@pytest.mark.parametrize("bus", ["", "default", " padded ", BUS.replace("000000000000", "bad")])
def test_eventbridge_requires_explicit_bus_arn(client: EventBridgeClient, bus: str) -> None:
    with pytest.raises(ValueError):
        EventBridgePublisher(client, bus)


@pytest.mark.parametrize(
    "change",
    [
        {"connect_timeout": 0},
        {"read_timeout": 6},
        {"read_timeout": float("inf")},
        {"retries": {"mode": "standard", "total_max_attempts": 2}},
        {"retries": {"mode": "adaptive", "total_max_attempts": 1}},
    ],
)
def test_eventbridge_rejects_unbounded_sdk_config(
    client: EventBridgeClient,
    change: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key, value in change.items():
        monkeypatch.setattr(client.meta.config, key, value)
    with pytest.raises(ValueError):
        publisher(client)


def test_eventbridge_rejects_wrong_sdk_service() -> None:
    wrong = Mock()
    wrong.meta.service_model.service_name = "s3"
    with pytest.raises(ValueError, match="EventBridge client"):
        EventBridgePublisher(wrong, BUS)
