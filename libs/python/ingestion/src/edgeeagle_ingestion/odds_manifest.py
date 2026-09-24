"""Bounded capture declarations for ADR-035, not an acquisition or rights authority."""

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Literal

from edgeeagle_domain._validation import aware_datetime, instance
from edgeeagle_domain.markets import MarketPeriod
from edgeeagle_domain.raw import RawPayloadIntegrityError, RawPayloadReference, RawPayloadStore

from .odds_api_parser import MAX_BOOKMAKERS, MAX_BYTES, NativeOddsEvent, parse_soccer_h2h


class OddsCaptureOrigin(Enum):
    AUTHORED_FIXTURE = "AUTHORED_FIXTURE"
    PROVIDER_CAPTURE = "PROVIDER_CAPTURE"


def _digest(value: str | None) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError("require a lowercase SHA-256 evidence reference")


def _token(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value):
        raise ValueError("require a bounded lowercase identifier")


@dataclass(frozen=True, kw_only=True)
class OddsSettlementProfile:
    """Declared regulation-time h2h interpretation for one requested bookmaker.

    Evidence hashes identify separately retained review documents, or authored
    fixture declarations. This record does not retrieve/authenticate those documents
    or certify real bookmaker rules. No live profiles ship with this module.
    """

    bookmaker_key: str
    version: str
    origin: OddsCaptureOrigin
    period: MarketPeriod
    evidence_sha256: str

    def __post_init__(self) -> None:
        _token(self.bookmaker_key)
        _token(self.version)
        instance(self.origin, OddsCaptureOrigin, "origin")
        if self.period is not MarketPeriod.REGULATION_TIME:
            raise ValueError("only explicit regulation-time settlement is supported")
        _digest(self.evidence_sha256)


@dataclass(frozen=True, kw_only=True)
class OddsCaptureManifest:
    """Exact raw reference plus a restricted, secret-free request description.

    Profiles supply the explicit requested bookmaker set; response subsets and
    empty results remain possible. Future normalization must reject undeclared
    bookmakers and bind profiles to mapped sportsbook venues. Only the current
    v4 sport-odds request subset is represented, not arbitrary query parameters.

    Genuine captures require separately reviewed rights evidence. A hash is a
    provenance reference, not permission, authentication or proof of document
    retention. Callers must obtain human approval before using actual captures.
    """

    raw: RawPayloadReference
    sport_key: str
    origin: OddsCaptureOrigin
    captured_at: datetime | None
    simulated_snapshot_at: datetime | None
    rights_evidence_sha256: str | None
    settlement_profiles: tuple[OddsSettlementProfile, ...]
    market: Literal["h2h"] = "h2h"
    odds_format: Literal["decimal"] = "decimal"
    date_format: Literal["iso"] = "iso"

    def __post_init__(self) -> None:
        instance(self.raw, RawPayloadReference, "raw")
        instance(self.origin, OddsCaptureOrigin, "origin")
        if not isinstance(self.sport_key, str) or not re.fullmatch(
            r"soccer_[a-z0-9_]{1,57}", self.sport_key
        ):
            raise ValueError("require a bounded soccer competition key")
        if (self.market, self.odds_format, self.date_format) != ("h2h", "decimal", "iso"):
            raise ValueError("only h2h/decimal/iso capture requests are supported")
        if self.raw.size_bytes > MAX_BYTES or self.raw.capture.resource != self.endpoint:
            raise ValueError("require bounded raw capture with exact credential-free endpoint")
        if self.raw.capture.available_at is not None:
            raise ValueError("this replay-only capture path requires unknown availability")
        for field in ("captured_at", "simulated_snapshot_at"):
            value = getattr(self, field)
            if value is not None:
                aware_datetime(value, field)
                object.__setattr__(self, field, value.astimezone(UTC))
        if self.origin is OddsCaptureOrigin.AUTHORED_FIXTURE:
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
            _digest(self.rights_evidence_sha256)
        instance(self.settlement_profiles, tuple, "settlement_profiles")
        if not 1 <= len(self.settlement_profiles) <= MAX_BOOKMAKERS:
            raise ValueError("require one to twenty explicit requested bookmaker profiles")
        for profile in self.settlement_profiles:
            instance(profile, OddsSettlementProfile, "settlement profile")
            if profile.origin is not self.origin:
                raise ValueError("settlement evidence origin must match capture origin")
        if len({p.bookmaker_key for p in self.settlement_profiles}) != len(
            self.settlement_profiles
        ):
            raise ValueError("duplicate requested bookmaker profile")
        object.__setattr__(
            self,
            "settlement_profiles",
            tuple(sorted(self.settlement_profiles, key=lambda p: p.bookmaker_key)),
        )

    @property
    def endpoint(self) -> str:
        return f"/v4/sports/{self.sport_key}/odds"

    @property
    def snapshot_at(self) -> datetime:
        value = (
            self.simulated_snapshot_at
            if self.origin is OddsCaptureOrigin.AUTHORED_FIXTURE
            else self.captured_at
        )
        assert value is not None  # Enforced by construction; never use the current clock.
        return value

    @property
    def usage(self) -> Literal["SYNTHETIC_ONLY", "REPLAY_ONLY"]:
        return (
            "SYNTHETIC_ONLY" if self.origin is OddsCaptureOrigin.AUTHORED_FIXTURE else "REPLAY_ONLY"
        )


def read_odds_capture(
    store: RawPayloadStore, manifest: OddsCaptureManifest
) -> tuple[NativeOddsEvent, ...]:
    """Read retained raw bytes once, verify integrity and validate the whole response.

    Run before opening reference or write transactions. Zero observations are
    valid; keep the manifest even when this returns an empty tuple. No acquisition,
    rights approval, canonical normalization or persistence occurs here.
    """
    instance(manifest, OddsCaptureManifest, "manifest")
    body = store.get(manifest.raw)
    if body is None:
        raise FileNotFoundError("retained odds capture is missing")
    if (
        len(body) != manifest.raw.size_bytes
        or hashlib.sha256(body).hexdigest() != manifest.raw.sha256
    ):
        raise RawPayloadIntegrityError("retained odds capture differs from manifest")
    events = parse_soccer_h2h(body, sport_key=manifest.sport_key, snapshot_at=manifest.snapshot_at)
    declared = {profile.bookmaker_key for profile in manifest.settlement_profiles}
    if any(book.bookmaker_key not in declared for event in events for book in event.bookmakers):
        raise ValueError("response contains an undeclared bookmaker")
    return events
