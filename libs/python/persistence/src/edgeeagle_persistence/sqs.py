"""Bounded SQS transport for the receipt-verification consumer."""

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, NoReturn

from edgeeagle_domain._validation import text as validate_text
from edgeeagle_domain.sports import EventId
from edgeeagle_ingestion.consumer import NotificationDelivery
from edgeeagle_ingestion.notifications import EventAccepted

if TYPE_CHECKING:
    from mypy_boto3_sqs import SQSClient


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _constant(value: str) -> NoReturn:
    raise ValueError("Nonfinite JSON constant")


def decode_eventbridge(body: str) -> EventAccepted:
    """Ignore additive fields, but never accept unknown versions or pending intents."""
    try:
        if not isinstance(body, str) or len(body.encode("utf-8")) > 96 * 1024:
            raise ValueError("SQS body exceeds application bound or is not text")
        wrapper = json.loads(body, object_pairs_hook=_object, parse_constant=_constant)
        if wrapper["source"] != "edgeeagle.ingestion" or wrapper["detail-type"] != "EventAccepted":
            raise ValueError("Unexpected EventBridge source/type")
        envelope = wrapper["detail"]
        if (
            envelope["event_type"] != "EventAccepted"
            or type(envelope["version"]) is not int
            or envelope["version"] != 1
        ):
            raise ValueError("Unsupported notification type/version")
        value = EventAccepted(
            event_id=envelope["event_id"],
            canonical_event_id=EventId(envelope["payload"]["canonical_event_id"]),
            acceptance_key=envelope["payload"]["acceptance_key"],
            occurred_at=datetime.fromisoformat(envelope["occurred_at"]),
            correlation_id=envelope["correlation_id"],
            causation_id=envelope["causation_id"],
        )
        value.to_envelope(published_at=datetime.fromisoformat(envelope["published_at"]))
        return value
    except (TypeError, KeyError, ValueError, RecursionError) as error:
        raise ValueError("Invalid delivered EventAccepted notification") from error


def _success(response: Mapping[str, Any]) -> None:
    metadata = response.get("ResponseMetadata")
    if not isinstance(metadata, Mapping) or metadata.get("HTTPStatusCode") != 200:
        raise RuntimeError("SQS response lacks acknowledgement")


@dataclass(frozen=True)
class QueueDepth:
    visible: int
    in_flight: int
    delayed: int

    def __post_init__(self) -> None:
        for count in (self.visible, self.in_flight, self.delayed):
            if type(count) is not int or count < 0:
                raise ValueError("Queue counts must be nonnegative integers")

    @property
    def has_messages(self) -> bool:
        return self.visible + self.in_flight + self.delayed > 0


class SqsNotificationQueue:
    """One short-poll receive or delete per call; caller owns clients and queue policies."""

    def __init__(self, client: "SQSClient", queue_url: str, *, visibility_timeout: int) -> None:
        validate_text(queue_url, "queue_url")
        if type(visibility_timeout) is not int or not 1 <= visibility_timeout <= 43200:
            raise ValueError("visibility_timeout must be integer seconds in [1, 43200]")
        if client.meta.service_model.service_name != "sqs":
            raise ValueError("SQS client required")
        config = client.meta.config
        retries = getattr(config, "retries", None) or {}
        if retries.get("mode") != "standard" or retries.get("total_max_attempts") != 1:
            raise ValueError("Use standard SDK retries with total_max_attempts=1")
        for key in ("connect_timeout", "read_timeout"):
            timeout = getattr(config, key, None)
            if (
                isinstance(timeout, bool)
                or not isinstance(timeout, (int, float))
                or not math.isfinite(timeout)
                or not 0 < timeout <= 5
            ):
                raise ValueError("Use positive connect/read timeouts of at most five seconds")
        self._client = client
        self._url = queue_url
        self._visibility = visibility_timeout

    def receive(self) -> NotificationDelivery | None:
        response = self._client.receive_message(
            QueueUrl=self._url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=0,
            VisibilityTimeout=self._visibility,
        )
        _success(response)
        messages = response.get("Messages", [])
        if not isinstance(messages, list) or len(messages) > 1:
            raise ValueError("Unexpected SQS message list")
        if not messages:
            return None
        try:
            return NotificationDelivery(
                notification=decode_eventbridge(messages[0]["Body"]),
                receipt_handle=messages[0]["ReceiptHandle"],
            )
        except (KeyError, TypeError) as error:
            raise ValueError("SQS message missing body/receipt handle") from error

    def acknowledge(self, delivery: NotificationDelivery) -> None:
        _success(
            self._client.delete_message(QueueUrl=self._url, ReceiptHandle=delivery.receipt_handle)
        )

    def depth(self) -> QueueDepth:
        response = self._client.get_queue_attributes(
            QueueUrl=self._url,
            AttributeNames=[
                "ApproximateNumberOfMessages",
                "ApproximateNumberOfMessagesNotVisible",
                "ApproximateNumberOfMessagesDelayed",
            ],
        )
        _success(response)
        try:
            attributes = response["Attributes"]
            return QueueDepth(
                int(attributes["ApproximateNumberOfMessages"]),
                int(attributes["ApproximateNumberOfMessagesNotVisible"]),
                int(attributes["ApproximateNumberOfMessagesDelayed"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("SQS queue depth is invalid or unavailable") from error
