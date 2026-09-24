"""Bounded Sportmonks capture declarations; not acquisition or rights approval."""

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Literal

from edgeeagle_domain._validation import aware_datetime, instance
from edgeeagle_domain.raw import RawPayloadIntegrityError, RawPayloadReference, RawPayloadStore

from .sportmonks_parser import MAX_BYTES, NativeSportmonksFixture, parse_scheduled_fixture


class SportmonksCaptureOrigin(Enum):
    AUTHORED_FIXTURE = "AUTHORED_FIXTURE"
    PROVIDER_CAPTURE = "PROVIDER_CAPTURE"


@dataclass(frozen=True, kw_only=True)
class SportmonksCaptureManifest:
    """Exact raw reference and restricted, credential-free request declaration.

    A rights digest references separately reviewed evidence: it is not permission,
    authentication or proof of document retention. Actual captures require human
    approval. This in-memory contract neither serializes nor persists a manifest.
    """

    raw: RawPayloadReference
    fixture_id: int
    origin: SportmonksCaptureOrigin
    captured_at: datetime | None
    simulated_snapshot_at: datetime | None
    rights_evidence_sha256: str | None
    include: Literal["participants;state"] = "participants;state"
    timezone: Literal["UTC"] = "UTC"

    def __post_init__(self) -> None:
        instance(self.raw, RawPayloadReference, "raw")
        instance(self.origin, SportmonksCaptureOrigin, "origin")
        if type(self.fixture_id) is not int or not 0 < self.fixture_id < 2**63:
            raise ValueError("fixture_id must be a positive signed-64-bit integer")
        if (self.include, self.timezone) != ("participants;state", "UTC"):
            raise ValueError("only participants;state with UTC requests are supported")
        if self.raw.size_bytes > MAX_BYTES or self.raw.capture.resource != self.endpoint:
            raise ValueError("require bounded raw capture with exact credential-free endpoint")
        if self.raw.capture.available_at is not None:
            raise ValueError("this replay-only capture path requires unknown availability")
        for field in ("captured_at", "simulated_snapshot_at"):
            value = getattr(self, field)
            if value is not None:
                aware_datetime(value, field)
                object.__setattr__(self, field, value.astimezone(UTC))
        if self.origin is SportmonksCaptureOrigin.AUTHORED_FIXTURE:
            if (
                self.captured_at is not None
                or self.simulated_snapshot_at is None
                or self.rights_evidence_sha256 is not None
            ):
                raise ValueError("authored fixtures require only a simulated capture clock")
        else:
            if self.captured_at is None or self.simulated_snapshot_at is not None:
                raise ValueError("provider captures require only an actual capture clock")
            if self.captured_at > self.raw.capture.ingested_at:
                raise ValueError("capture time must not exceed raw ingestion time")
            if not isinstance(self.rights_evidence_sha256, str) or not re.fullmatch(
                r"[0-9a-f]{64}", self.rights_evidence_sha256
            ):
                raise ValueError("require a lowercase SHA-256 rights evidence reference")

    @property
    def endpoint(self) -> str:
        return f"/v3/football/fixtures/{self.fixture_id}"

    @property
    def snapshot_at(self) -> datetime:
        value = (
            self.simulated_snapshot_at
            if self.origin is SportmonksCaptureOrigin.AUTHORED_FIXTURE
            else self.captured_at
        )
        assert value is not None  # Enforced at construction; never use the current clock.
        return value

    @property
    def usage(self) -> Literal["SYNTHETIC_ONLY", "REPLAY_ONLY"]:
        return (
            "SYNTHETIC_ONLY"
            if self.origin is SportmonksCaptureOrigin.AUTHORED_FIXTURE
            else "REPLAY_ONLY"
        )


def read_sportmonks_capture(
    store: RawPayloadStore, manifest: SportmonksCaptureManifest
) -> NativeSportmonksFixture:
    """Read once and verify retained bytes before parsing native fixture evidence.

    No acquisition, current clock, canonical mapping, database access or writes.
    The caller retains the manifest; native output alone is not a replay receipt.
    """
    instance(manifest, SportmonksCaptureManifest, "manifest")
    body = store.get(manifest.raw)
    if body is None:
        raise FileNotFoundError("retained Sportmonks capture is missing")
    if (
        len(body) != manifest.raw.size_bytes
        or hashlib.sha256(body).hexdigest() != manifest.raw.sha256
    ):
        raise RawPayloadIntegrityError("retained Sportmonks capture differs from manifest")
    return parse_scheduled_fixture(
        body, expected_fixture_id=manifest.fixture_id, snapshot_at=manifest.snapshot_at
    )
