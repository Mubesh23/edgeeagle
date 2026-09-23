"""Canonical candidate output, not a persisted or historically eligible event."""

from dataclasses import dataclass

from edgeeagle_domain.mappings import ProviderEntityKey
from edgeeagle_domain.raw import RawPayloadReference
from edgeeagle_domain.sports import Event, EventParticipant


@dataclass(frozen=True, kw_only=True)
class EventCandidate:
    event: Event
    entries: tuple[EventParticipant, ...]
    raw: RawPayloadReference
    provider_key: ProviderEntityKey
    parser_version: str
    normalizer_version: str
    context_version: str
