import json
from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from unittest.mock import Mock

import boto3
import pytest
from botocore.config import Config
from botocore.stub import Stubber
from mypy_boto3_sqs import SQSClient

from edgeeagle_ingestion.consumer import NotificationDelivery
from edgeeagle_persistence.sqs import QueueDepth, SqsNotificationQueue, decode_eventbridge
from tests.unit.test_event_notifications import notification

URL = "http://127.0.0.1:4566/000000000000/test"
OK = {"HTTPStatusCode": 200}


def body() -> dict[str, Any]:
    value = notification()
    return {
        "source": "edgeeagle.ingestion",
        "detail-type": "EventAccepted",
        "detail": value.to_envelope(published_at=value.occurred_at),
    }


def test_sqs_decode_additive_fields_and_attempt_timestamps() -> None:
    value = body()
    value["new_transport_field"] = True
    value["detail"]["new_field"] = {"anything": []}
    value["detail"]["payload"]["new_field"] = "ignored"
    value["detail"]["published_at"] = (
        notification().occurred_at + timedelta(seconds=10)
    ).isoformat()
    assert decode_eventbridge(json.dumps(value)) == notification()


@pytest.mark.parametrize(
    "raw", ["", "[]", "null", "{", '{"a":1,"a":2}', '{"a":NaN}', '"' + "x" * 100000 + '"']
)
def test_sqs_rejects_malformed_json(raw: str) -> None:
    with pytest.raises(ValueError):
        decode_eventbridge(raw)


@pytest.mark.parametrize(
    "field,value",
    [
        ("version", 2),
        ("version", True),
        ("published_at", None),
        ("published_at", "2000-01-01T00:00:00+00:00"),
        ("published_at", "2026-09-23"),
        ("event_type", "Other"),
        ("event_id", ""),
        ("payload", {}),
        ("occurred_at", None),
        ("acceptance_key", "bad"),
    ],
)
def test_sqs_rejects_invalid_known_fields(field: str, value: Any) -> None:
    wrapped = body()
    if field == "acceptance_key":
        wrapped["detail"]["payload"][field] = value
    else:
        wrapped["detail"][field] = value
    with pytest.raises(ValueError):
        decode_eventbridge(json.dumps(wrapped))


@pytest.mark.parametrize(
    "change", [{"source": "other"}, {"detail-type": "Other"}, {"detail": []}, {"detail": None}]
)
def test_sqs_rejects_other_sources(change: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        decode_eventbridge(json.dumps(body() | change))


@pytest.fixture
def client() -> Iterator[SQSClient]:
    value = boto3.client(
        "sqs",
        endpoint_url="http://127.0.0.1:4566",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        aws_session_token="test",
        config=Config(
            connect_timeout=2,
            read_timeout=3,
            proxies={},
            retries={"mode": "standard", "total_max_attempts": 1},
        ),
    )
    try:
        yield value
    finally:
        value.close()


def test_sqs_receive_delete_and_depth(client: SQSClient) -> None:
    queue = SqsNotificationQueue(client, URL, visibility_timeout=30)
    with Stubber(client) as stubber:
        stubber.add_response(
            "receive_message",
            {
                "ResponseMetadata": OK,
                "Messages": [
                    {
                        "Body": json.dumps(body()),
                        "ReceiptHandle": "latest",
                    }
                ],
            },
            {
                "QueueUrl": URL,
                "MaxNumberOfMessages": 1,
                "WaitTimeSeconds": 0,
                "VisibilityTimeout": 30,
            },
        )
        value = queue.receive()
        assert value == NotificationDelivery(notification=notification(), receipt_handle="latest")
        stubber.add_response(
            "delete_message", {"ResponseMetadata": OK}, {"QueueUrl": URL, "ReceiptHandle": "latest"}
        )
        queue.acknowledge(value)
        stubber.add_response("receive_message", {"ResponseMetadata": OK})
        assert queue.receive() is None
        stubber.add_response(
            "get_queue_attributes",
            {
                "ResponseMetadata": OK,
                "Attributes": {
                    "ApproximateNumberOfMessages": "1",
                    "ApproximateNumberOfMessagesNotVisible": "2",
                    "ApproximateNumberOfMessagesDelayed": "3",
                },
            },
        )
        depth = queue.depth()
        assert (depth.visible, depth.in_flight, depth.delayed) == (1, 2, 3)
        assert depth.has_messages
        stubber.assert_no_pending_responses()


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"ResponseMetadata": {"HTTPStatusCode": 500}},
        {"ResponseMetadata": OK, "Messages": [{}, {}]},
        {"ResponseMetadata": OK, "Messages": [{}]},
    ],
)
def test_sqs_bad_responses_never_become_empty_success(
    client: SQSClient,
    response: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(client, "receive_message", Mock(return_value=response))
    with pytest.raises((ValueError, RuntimeError)):
        SqsNotificationQueue(client, URL, visibility_timeout=30).receive()


def test_sqs_failed_delete_propagates(client: SQSClient) -> None:
    with Stubber(client) as stubber:
        stubber.add_response("delete_message", {"ResponseMetadata": {"HTTPStatusCode": 500}})
        with pytest.raises(RuntimeError):
            SqsNotificationQueue(client, URL, visibility_timeout=30).acknowledge(
                NotificationDelivery(notification=notification(), receipt_handle="h")
            )


@pytest.mark.parametrize("visibility", [0, True, 43201])
def test_sqs_visibility_guards(client: SQSClient, visibility: int) -> None:
    with pytest.raises(ValueError):
        SqsNotificationQueue(client, URL, visibility_timeout=visibility)


@pytest.mark.parametrize(
    "key,value",
    [
        ("read_timeout", 0),
        ("read_timeout", None),
        ("connect_timeout", float("nan")),
        ("retries", {"mode": "adaptive", "total_max_attempts": 1}),
        ("retries", {"mode": "standard", "total_max_attempts": 2}),
    ],
)
def test_sqs_sdk_bounds(
    client: SQSClient, key: str, value: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(client.meta.config, key, value)
    with pytest.raises(ValueError):
        SqsNotificationQueue(client, URL, visibility_timeout=30)


def test_sqs_requires_correct_sdk_service() -> None:
    client = Mock()
    client.meta.service_model.service_name = "events"
    with pytest.raises(ValueError, match="SQS client"):
        SqsNotificationQueue(client, URL, visibility_timeout=30)


def test_sqs_depth_missing_or_negative_is_not_healthy(client: SQSClient) -> None:
    with Stubber(client) as stubber:
        for attributes in (
            {},
            {
                "ApproximateNumberOfMessages": "-1",
                "ApproximateNumberOfMessagesNotVisible": "0",
                "ApproximateNumberOfMessagesDelayed": "0",
            },
        ):
            stubber.add_response(
                "get_queue_attributes", {"ResponseMetadata": OK, "Attributes": attributes}
            )
            with pytest.raises(ValueError, match="depth"):
                SqsNotificationQueue(client, URL, visibility_timeout=30).depth()
    assert not QueueDepth(0, 0, 0).has_messages
