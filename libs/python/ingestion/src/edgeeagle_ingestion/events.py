"""Canonical candidate output, not a persisted or historically eligible event."""

from dataclasses import dataclass
from typing import Protocol

from edgeeagle_domain._validation import instance, text
from edgeeagle_domain.mappings import ProviderEntityKey
from edgeeagle_domain.raw import RawPayloadReference
from edgeeagle_domain.sports import Event, EventId, EventParticipant


@dataclass(frozen=True, kw_only=True)
class EventCandidate:
    event: Event
    entries: tuple[EventParticipant, ...]
    raw: RawPayloadReference
    provider_key: ProviderEntityKey
    parser_version: str
    normalizer_version: str
    context_version: str

    def __post_init__(self) -> None:
        instance(self.event, Event, "event")
        instance(self.entries, tuple, "entries")
        instance(self.raw, RawPayloadReference, "raw")
        instance(self.provider_key, ProviderEntityKey, "provider_key")
        for name in ("parser_version", "normalizer_version", "context_version"):
            text(getattr(self, name), name)
        if self.provider_key.data_source_id != self.raw.capture.data_source_id:
            raise ValueError("provider key and raw capture must have the same source")
        if self.provider_key.provider_entity_type != "event":
            raise ValueError("provider key must identify an event")
        if not self.entries:
            raise ValueError("event requires participant entries")
        for entry in self.entries:
            instance(entry, EventParticipant, "entry")
            if entry.event_id != self.event.event_id:
                raise ValueError("entry must belong to candidate event")
        if len({entry.participant_id for entry in self.entries}) != len(self.entries):
            raise ValueError("duplicate participant entries")


class EventAcceptanceConflict(Exception):
    """Existing event or acquisition identity differs from the proposed acceptance."""


class EventAcceptanceRepository(Protocol):
    def accept(self, candidate: EventCandidate) -> bool:
        """True for initial insertion, False for exact replay; never overwrite."""
        ...

    def get(self, event_id: EventId) -> EventCandidate | None:
        """Return the immutable accepted output, not current mutable event state."""
        ...
