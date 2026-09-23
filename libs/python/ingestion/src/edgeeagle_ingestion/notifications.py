"""EventAccepted v1 publication intent; no transport or persistence dependencies."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from edgeeagle_domain._validation import aware_datetime, instance, text
from edgeeagle_domain.sports import EventId
from edgeeagle_ingestion.events import EventCandidate
from edgeeagle_ingestion.identity import acceptance_key


@dataclass(frozen=True, kw_only=True)
class EventAccepted:
    event_id: str
    canonical_event_id: EventId
    acceptance_key: str
    occurred_at: datetime
    correlation_id: str
    causation_id: str

    def __post_init__(self) -> None:
        for name in ("event_id", "correlation_id", "causation_id"):
            text(getattr(self, name), name)
        instance(self.canonical_event_id, EventId, "canonical_event_id")
        if not isinstance(self.acceptance_key, str) or not re.fullmatch(
            "[0-9a-f]{64}", self.acceptance_key
        ):
            raise ValueError("acceptance_key must be a lowercase SHA-256 digest")
        aware_datetime(self.occurred_at, "occurred_at")
        object.__setattr__(self, "occurred_at", self.occurred_at.astimezone(UTC))

    @classmethod
    def for_candidate(
        cls,
        candidate: EventCandidate,
        *,
        event_id: str,
        occurred_at: datetime,
        correlation_id: str,
        causation_id: str,
    ) -> "EventAccepted":
        instance(candidate, EventCandidate, "candidate")
        aware_datetime(occurred_at, "occurred_at")
        if occurred_at < candidate.raw.capture.ingested_at:
            raise ValueError("acceptance occurrence must not precede raw ingestion")
        return cls(
            event_id=event_id,
            canonical_event_id=candidate.event.event_id,
            acceptance_key=acceptance_key(candidate),
            occurred_at=occurred_at,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )

    def to_envelope(self, *, published_at: datetime | None = None) -> dict[str, Any]:
        if published_at is not None:
            aware_datetime(published_at, "published_at")
            if published_at < self.occurred_at:
                raise ValueError("publication must not precede occurrence")
        return {
            "event_id": self.event_id,
            "event_type": "EventAccepted",
            "version": 1,
            "occurred_at": self.occurred_at.isoformat(),
            "published_at": None
            if published_at is None
            else published_at.astimezone(UTC).isoformat(),
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "payload": {
                "canonical_event_id": self.canonical_event_id.value,
                "acceptance_key": self.acceptance_key,
            },
        }

    @classmethod
    def from_envelope(cls, envelope: Any) -> "EventAccepted":
        """Read canonical pending intents, never infer transport acknowledgement."""
        try:
            if envelope["published_at"] is not None:
                raise ValueError("expected pending intent")
            if type(envelope["version"]) is not int or envelope["version"] != 1:
                raise ValueError("unsupported version")
            result = cls(
                event_id=envelope["event_id"],
                canonical_event_id=EventId(envelope["payload"]["canonical_event_id"]),
                acceptance_key=envelope["payload"]["acceptance_key"],
                occurred_at=datetime.fromisoformat(envelope["occurred_at"]),
                correlation_id=envelope["correlation_id"],
                causation_id=envelope["causation_id"],
            )
            if result.to_envelope() != envelope:
                raise ValueError("noncanonical intent")
            return result
        except (TypeError, KeyError, ValueError) as error:
            raise ValueError("Invalid pending EventAccepted envelope") from error


class EventPublicationRepository(Protocol):
    def accept_with_notification(
        self, candidate: EventCandidate, notification: EventAccepted
    ) -> bool:
        """Atomically accept output and publication intent; False only for exact replay."""
        ...

    def get_notification(self, event_id: EventId) -> EventAccepted | None: ...
