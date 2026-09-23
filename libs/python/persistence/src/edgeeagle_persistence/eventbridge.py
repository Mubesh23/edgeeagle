"""Single-entry outbox transport; no database or resource lifecycle ownership."""

import json
import math
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from botocore.exceptions import (
    ClientError,
    ConnectionClosedError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)

from edgeeagle_domain._validation import aware_datetime, instance
from edgeeagle_ingestion.delivery import DeliveryClaim, DeliveryLeaseLost
from edgeeagle_ingestion.dispatch import RetryablePublicationError

if TYPE_CHECKING:
    from mypy_boto3_events import EventBridgeClient

_BUS = re.compile(r"arn:aws(?:-[a-z]+)*:events:[a-z0-9-]+:[0-9]{12}:event-bus/[A-Za-z0-9_.-]+")
_TRANSIENT = {"InternalFailure", "InternalException", "ThrottlingException"}


class EventBridgePublicationError(Exception):
    """Destination or entry rejected; intervention is required before retrying."""


def _request(call: Callable[[], Mapping[str, Any]]) -> Mapping[str, Any]:
    try:
        response = call()
    except (
        ConnectionClosedError,
        ConnectTimeoutError,
        EndpointConnectionError,
        ReadTimeoutError,
    ) as e:
        raise RetryablePublicationError("EventBridge connection outcome unknown") from e
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        status = e.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
        if code in _TRANSIENT or status == 429 or 500 <= status <= 599:
            raise RetryablePublicationError("EventBridge transient request failure") from e
        raise
    if not isinstance(response, Mapping):
        raise RetryablePublicationError("EventBridge response is malformed")
    metadata = response.get("ResponseMetadata")
    if not isinstance(metadata, Mapping) or metadata.get("HTTPStatusCode") != 200:
        raise RetryablePublicationError("EventBridge response lacks HTTP acceptance")
    return response


class EventBridgePublisher:
    """Caller supplies and closes a configured client; SDK retries must be disabled."""

    def __init__(
        self,
        client: "EventBridgeClient",
        bus_arn: str,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if not isinstance(bus_arn, str) or _BUS.fullmatch(bus_arn) is None:
            raise ValueError("bus_arn must identify an explicit standard/custom EventBridge bus")
        if client.meta.service_model.service_name != "events":
            raise ValueError("client must be an EventBridge client")
        config = client.meta.config
        # Botocore creates these attributes dynamically; its stubs omit them.
        retries = getattr(config, "retries", None) or {}
        if retries.get("mode") != "standard" or retries.get("total_max_attempts") != 1:
            raise ValueError("use standard retries with total_max_attempts=1")
        timeouts = (getattr(config, "connect_timeout", None), getattr(config, "read_timeout", None))
        call_allowance = 0.0
        for timeout in timeouts:
            if (
                isinstance(timeout, bool)
                or not isinstance(timeout, (int, float))
                or not math.isfinite(timeout)
                or not 0 < timeout <= 5
            ):
                raise ValueError("connect/read timeouts must be positive and at most five seconds")
            call_allowance += timeout
        self._call_allowance = call_allowance
        self._client = client
        self._bus_arn = bus_arn
        self._clock = clock

    def _now(self, claim: DeliveryClaim, *, calls: int) -> datetime:
        now = self._clock()
        aware_datetime(now, "publication clock")
        now = now.astimezone(UTC)
        if now < claim.claimed_at:
            raise ValueError("publication clock precedes database claim time")
        allowance = timedelta(seconds=calls * self._call_allowance + 1)
        if now + allowance >= claim.lease_expires_at:
            raise DeliveryLeaseLost("insufficient remaining lease for EventBridge request")
        return now

    @staticmethod
    def _detail(claim: DeliveryClaim, now: datetime) -> str:
        detail = json.dumps(
            claim.notification.to_envelope(published_at=now),
            separators=(",", ":"),
            ensure_ascii=False,
        )
        if len(detail.encode("utf-8")) > 64 * 1024:
            raise ValueError("EventBridge detail exceeds application limit of 64 KiB")
        return detail

    def publish(self, claim: DeliveryClaim) -> None:
        instance(claim, DeliveryClaim, "claim")
        # Fail oversized/expired inputs before any network call.
        self._detail(claim, self._now(claim, calls=2))
        bus = _request(lambda: self._client.describe_event_bus(Name=self._bus_arn))
        if bus.get("Arn") != self._bus_arn:
            raise EventBridgePublicationError("EventBridge destination ARN mismatch")
        detail = self._detail(claim, self._now(claim, calls=1))
        response = _request(
            lambda: self._client.put_events(
                Entries=[
                    {
                        "EventBusName": self._bus_arn,
                        "Source": "edgeeagle.ingestion",
                        "DetailType": "EventAccepted",
                        "Time": claim.notification.occurred_at,
                        "Detail": detail,
                    }
                ]
            )
        )
        entries = response.get("Entries")
        failed = response.get("FailedEntryCount")
        if (
            not isinstance(entries, list)
            or len(entries) != 1
            or not isinstance(entries[0], Mapping)
            or type(failed) is not int
            or failed not in (0, 1)
        ):
            raise RetryablePublicationError("EventBridge entry result is malformed")
        entry = entries[0]
        code = entry.get("ErrorCode")
        if failed == 1 and isinstance(code, str) and code and "EventId" not in entry:
            if code in {"InternalFailure", "ThrottlingException"}:
                raise RetryablePublicationError("EventBridge transient entry failure")
            raise EventBridgePublicationError("EventBridge rejected entry; inspect configuration")
        event_id = entry.get("EventId")
        if (
            failed != 0
            or "ErrorCode" in entry
            or "ErrorMessage" in entry
            or not isinstance(event_id, str)
            or not event_id
            or event_id != event_id.strip()
        ):
            raise RetryablePublicationError("EventBridge acceptance is ambiguous")
