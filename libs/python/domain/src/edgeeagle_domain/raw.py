"""Provider-neutral raw capture identity; no storage or provider dependencies."""

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from edgeeagle_domain._validation import aware_datetime, instance, text
from edgeeagle_domain.provenance import DataSourceId


@dataclass(frozen=True, kw_only=True)
class RawCapture:
    data_source_id: DataSourceId
    resource: str
    ingested_at: datetime
    effective_at: datetime | None = None
    observed_at: datetime | None = None
    available_at: datetime | None = None

    def __post_init__(self) -> None:
        instance(self.data_source_id, DataSourceId, "data_source_id")
        text(self.resource, "resource")
        aware_datetime(self.ingested_at, "ingested_at")
        for name in ("ingested_at", "effective_at", "observed_at", "available_at"):
            value = getattr(self, name)
            if value is not None:
                aware_datetime(value, name)
                object.__setattr__(self, name, value.astimezone(UTC))
        if self.available_at is not None and self.available_at > self.ingested_at:
            raise ValueError("availability must not exceed ingestion time")


@dataclass(frozen=True, kw_only=True)
class RawPayloadReference:
    capture: RawCapture
    sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        instance(self.capture, RawCapture, "capture")
        if not isinstance(self.sha256, str) or not re.fullmatch("[0-9a-f]{64}", self.sha256):
            raise ValueError("sha256 must be a lowercase SHA-256 hex digest")
        if type(self.size_bytes) is not int or self.size_bytes < 0:
            raise ValueError("size_bytes must be a nonnegative integer")


@dataclass(frozen=True, kw_only=True)
class RawPayload:
    capture: RawCapture
    body: bytes

    def __post_init__(self) -> None:
        instance(self.capture, RawCapture, "capture")
        instance(self.body, bytes, "body")

    def reference(self) -> RawPayloadReference:
        return RawPayloadReference(
            capture=self.capture,
            sha256=hashlib.sha256(self.body).hexdigest(),
            size_bytes=len(self.body),
        )


class RawPayloadIntegrityError(Exception):
    """Stored bytes or provenance differ from the expected immutable capture."""


class RawPayloadStore(Protocol):
    def put(self, payload: RawPayload) -> RawPayloadReference: ...

    def get(self, reference: RawPayloadReference) -> bytes | None: ...
