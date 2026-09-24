"""Read-only Sportmonks identities and selected mapping evidence (ADR-037)."""

import re
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from edgeeagle_domain._validation import aware_datetime, instance
from edgeeagle_domain.consistency import validate_event_context
from edgeeagle_domain.mapping_repository import MappingRepository
from edgeeagle_domain.mappings import (
    MappingStatus,
    ProviderEntityKey,
    ProviderMappingRevision,
    resolve_mapping,
)
from edgeeagle_domain.provenance import DataSource, SourceType
from edgeeagle_domain.repositories import DataSourceRepository
from edgeeagle_domain.sports import Event, EventId, EventParticipant
from edgeeagle_domain.sports_repository import SportsRepository

from .fixture_references import (
    FixtureReferenceKeys,
    ResolvedFixtureReferences,
    resolve_fixture_references,
)


@dataclass(frozen=True, kw_only=True)
class SportmonksReferenceKeys:
    context: FixtureReferenceKeys
    event: ProviderEntityKey

    def ordered(self) -> tuple[ProviderEntityKey, ...]:
        return *self.context.ordered(), self.event

    def __post_init__(self) -> None:
        instance(self.context, FixtureReferenceKeys, "context")
        instance(self.event, ProviderEntityKey, "event")
        if self.event.data_source_id != self.context.sport.data_source_id:
            raise ValueError("reference keys must share a source")
        kinds = ("sport", "league", "season", "participant", "participant", "fixture")
        for key, kind in zip(self.ordered(), kinds, strict=True):
            if (
                key.provider_entity_type != kind
                or not re.fullmatch(r"[1-9][0-9]{0,18}", key.provider_entity_id)
                or int(key.provider_entity_id) >= 2**63
            ):
                raise ValueError("require exact Sportmonks namespace and positive native ID")
        if self.context.sport.provider_entity_id != "1":
            raise ValueError("only Sportmonks soccer sport ID 1 is supported")


@dataclass(frozen=True, kw_only=True)
class ResolvedSportmonksReferences:
    """Captured current context, not historical eligibility or a durable receipt."""

    context: ResolvedFixtureReferences
    source: DataSource
    event: Event
    entries: tuple[EventParticipant, ...]
    event_revision: ProviderMappingRevision

    @property
    def as_of(self) -> datetime:
        return self.context.as_of

    @property
    def revisions(self) -> tuple[ProviderMappingRevision, ...]:
        return *self.context.revisions, self.event_revision

    def __post_init__(self) -> None:
        instance(self.context, ResolvedFixtureReferences, "context")
        instance(self.source, DataSource, "source")
        instance(self.event_revision, ProviderMappingRevision, "event_revision")
        instance(self.entries, tuple, "entries")
        c = self.context
        validate_event_context(
            event=self.event,
            sport=c.sport,
            competition=c.competition,
            season=c.season,
            participants=(c.home, c.away),
            entries=self.entries,
        )
        if (
            self.source.code != "SPORTMONKS"
            or self.source.source_type is not SourceType.SPORTS_DATA
        ):
            raise ValueError("require the registered Sportmonks sports-data source")
        if c.sport.code != "soccer" or any(p.participant_type != "TEAM" for p in (c.home, c.away)):
            raise ValueError("require soccer team participants")
        if {(e.role, e.participant_id) for e in self.entries} != {
            ("HOME", c.home.participant_id),
            ("AWAY", c.away.participant_id),
        }:
            raise ValueError("require exact mapped HOME/AWAY roles")
        row = self.event_revision
        if row.canonical_entity_id != self.event.event_id:
            raise ValueError("event mapping target differs from canonical event")
        if row.status is not MappingStatus.MAPPED or row.available_at > self.as_of:
            raise ValueError("event mapping must be active and available at cutoff")
        if any(r.key.data_source_id != self.source.data_source_id for r in self.revisions):
            raise ValueError("mapping source differs from canonical source")
        SportmonksReferenceKeys(
            context=FixtureReferenceKeys(
                sport=c.revisions[0].key,
                competition=c.revisions[1].key,
                season=c.revisions[2].key,
                home=c.revisions[3].key,
                away=c.revisions[4].key,
            ),
            event=row.key,
        )
        object.__setattr__(
            self, "entries", tuple(sorted(self.entries, key=lambda e: e.role != "HOME"))
        )


class SportmonksReferenceResolver(Protocol):
    def resolve(
        self, keys: SportmonksReferenceKeys, *, as_of: datetime
    ) -> ResolvedSportmonksReferences: ...


SportmonksReferenceReads = Callable[[], AbstractContextManager[SportmonksReferenceResolver]]


def resolve_sportmonks_references(
    keys: SportmonksReferenceKeys,
    mappings: MappingRepository,
    sports: SportsRepository,
    sources: DataSourceRepository,
    *,
    as_of: datetime,
) -> ResolvedSportmonksReferences:
    """Caller supplies repositories from one pinned read-only snapshot.

    Resolve all six complete histories; never insert, match labels, or retry.
    Capture/native checks belong to normalization after this context is selected.
    """
    instance(keys, SportmonksReferenceKeys, "keys")
    aware_datetime(as_of, "as_of")
    source = sources.get(keys.event.data_source_id)
    if source is None or source.data_source_id != keys.event.data_source_id:
        raise ValueError("source reference is missing or mismatched")
    context = resolve_fixture_references(keys.context, mappings, sports, as_of=as_of)
    row = resolve_mapping(keys.event, mappings.history(keys.event), as_of=context.as_of)
    if row is None:
        raise ValueError("event mapping is missing, revoked, or not yet available")
    if not isinstance(row.canonical_entity_id, EventId):
        raise ValueError("event mapping has the wrong target type")
    event = sports.get_event(row.canonical_entity_id)
    if event is None:
        raise ValueError("mapped event reference is missing")
    return ResolvedSportmonksReferences(
        context=context,
        source=source,
        event=event,
        entries=tuple(sports.get_event_participants(event.event_id)),
        event_revision=row,
    )
