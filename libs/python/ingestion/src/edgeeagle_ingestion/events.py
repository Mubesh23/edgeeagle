"""Canonical candidate output, not a persisted or historically eligible event."""

from dataclasses import dataclass
from typing import Protocol

from edgeeagle_domain._validation import instance, text
from edgeeagle_domain.consistency import validate_event_context
from edgeeagle_domain.mappings import ProviderEntityKey
from edgeeagle_domain.raw import RawPayloadReference
from edgeeagle_domain.sports import Event, EventId, EventParticipant
from edgeeagle_ingestion.fixture_references import ResolvedFixtureReferences


@dataclass(frozen=True, kw_only=True)
class FixtureMappingEvidence:
    """Captured resolution and explicit label guards, not authenticated review proof.

    Event ID, status, source event key, and context version remain on the enclosing
    candidate. The caller must retain the raw bytes and use a pinned read snapshot.
    """

    references: ResolvedFixtureReferences
    competition_key: str
    home_label: str
    away_label: str

    def __post_init__(self) -> None:
        instance(self.references, ResolvedFixtureReferences, "references")
        for name in ("competition_key", "home_label", "away_label"):
            text(getattr(self, name), name)
        if self.home_label == self.away_label:
            raise ValueError("home and away label guards must be distinct")


@dataclass(frozen=True, kw_only=True)
class SoccerResultEvidence:
    """Recorded full-time score and asserted local-time offset; never settlement."""

    home_goals: int
    away_goals: int
    utc_offset_minutes: int

    def __post_init__(self) -> None:
        for name, low, high in (
            ("home_goals", 0, 99),
            ("away_goals", 0, 99),
            ("utc_offset_minutes", -840, 840),
        ):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"invalid {name}")


@dataclass(frozen=True, kw_only=True)
class EventCandidate:
    event: Event
    entries: tuple[EventParticipant, ...]
    raw: RawPayloadReference
    provider_key: ProviderEntityKey
    parser_version: str
    normalizer_version: str
    context_version: str
    mapping_evidence: FixtureMappingEvidence | None = None
    soccer_result: SoccerResultEvidence | None = None

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
        if self.soccer_result is not None:
            instance(self.soccer_result, SoccerResultEvidence, "soccer_result")
            if self.mapping_evidence is None or self.event.status != "FINISHED":
                raise ValueError("soccer results require mapped finished events")
        if self.mapping_evidence is not None:
            instance(self.mapping_evidence, FixtureMappingEvidence, "mapping_evidence")
            refs = self.mapping_evidence.references
            if self.soccer_result is not None and (
                refs.sport.code != "soccer"
                or refs.home.participant_type != "TEAM"
                or refs.away.participant_type != "TEAM"
            ):
                raise ValueError("soccer results require soccer team context")
            if refs.revisions[0].key.data_source_id != self.provider_key.data_source_id:
                raise ValueError("mapping evidence and candidate must share a source")
            validate_event_context(
                event=self.event,
                sport=refs.sport,
                competition=refs.competition,
                season=refs.season,
                participants=(refs.home, refs.away),
                entries=self.entries,
            )
            if {(entry.participant_id, entry.role) for entry in self.entries} != {
                (refs.home.participant_id, "HOME"),
                (refs.away.participant_id, "AWAY"),
            }:
                raise ValueError("mapping evidence must match HOME/AWAY entries")


class EventAcceptanceConflict(Exception):
    """Existing event or acquisition identity differs from the proposed acceptance."""


class EventAcceptanceRepository(Protocol):
    def accept(self, candidate: EventCandidate) -> bool:
        """True for initial insertion, False for exact replay; never overwrite."""
        ...

    def get(self, event_id: EventId) -> EventCandidate | None:
        """Return the immutable accepted output, not current mutable event state."""
        ...
