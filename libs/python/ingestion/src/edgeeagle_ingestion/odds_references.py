"""Explicit preexisting soccer/bookmaker references for ADR-035; no label matching."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, TypeVar

from edgeeagle_domain._validation import aware_datetime, instance
from edgeeagle_domain.consistency import validate_event_context
from edgeeagle_domain.mapping_repository import MappingRepository
from edgeeagle_domain.mappings import (
    MappingStatus,
    ProviderEntityKey,
    ProviderMappingRevision,
    resolve_mapping,
)
from edgeeagle_domain.provenance import DataSource, SourceType, Venue, VenueId, VenueType
from edgeeagle_domain.repositories import DataSourceRepository, VenueRepository
from edgeeagle_domain.sports import (
    Competition,
    CompetitionId,
    Event,
    EventId,
    EventParticipant,
    Participant,
    Season,
    Sport,
)
from edgeeagle_domain.sports_repository import SportsRepository


@dataclass(frozen=True, kw_only=True)
class OddsReferenceKeys:
    competition: ProviderEntityKey
    event: ProviderEntityKey
    venues: tuple[ProviderEntityKey, ...]

    def ordered(self) -> tuple[ProviderEntityKey, ...]:
        return self.competition, self.event, *self.venues

    def __post_init__(self) -> None:
        instance(self.venues, tuple, "venues")
        if len(self.venues) > 20:
            raise ValueError("at most twenty venue keys")
        for key in self.ordered():
            instance(key, ProviderEntityKey, "key")
        if len(set(self.ordered())) != len(self.ordered()):
            raise ValueError("reference keys must be distinct")
        if len({k.data_source_id for k in self.ordered()}) != 1:
            raise ValueError("reference keys must share a source")


@dataclass(frozen=True, kw_only=True)
class ResolvedOddsReferences:
    """Immutable in-memory evidence, not a historical-availability or rights claim.

    Revisions are ordered competition, event, then venues in caller key order.
    Label guards, capture evidence and receipt serialization remain separate.
    """

    source: DataSource
    sport: Sport
    competition: Competition
    season: Season
    event: Event
    home: Participant
    away: Participant
    entries: tuple[EventParticipant, ...]
    venues: tuple[Venue, ...]
    revisions: tuple[ProviderMappingRevision, ...]
    as_of: datetime

    def __post_init__(self) -> None:
        aware_datetime(self.as_of, "as_of")
        object.__setattr__(self, "as_of", self.as_of.astimezone(UTC))
        instance(self.source, DataSource, "source")
        for values in (self.entries, self.venues, self.revisions):
            instance(values, tuple, "evidence collection")
        validate_event_context(
            event=self.event,
            sport=self.sport,
            competition=self.competition,
            season=self.season,
            participants=(self.home, self.away),
            entries=self.entries,
        )
        if (
            self.source.code != "THE_ODDS_API"
            or self.source.source_type is not SourceType.ODDS_AGGREGATOR
        ):
            raise ValueError("require The Odds API aggregator source")
        if self.sport.code != "soccer" or any(
            p.participant_type != "TEAM" for p in (self.home, self.away)
        ):
            raise ValueError("require soccer team participants")
        expected_entries = {("HOME", self.home.participant_id), ("AWAY", self.away.participant_id)}
        if {(e.role, e.participant_id) for e in self.entries} != expected_entries:
            raise ValueError("require exact HOME/AWAY participant roles")
        for venue in self.venues:
            instance(venue, Venue, "venue")
            if venue.venue_type is not VenueType.SPORTSBOOK:
                raise ValueError("require sportsbook venues")
        if len({v.venue_id for v in self.venues}) != len(self.venues):
            raise ValueError("bookmaker mappings must not collapse to one venue")
        if len(self.revisions) != 2 + len(self.venues):
            raise ValueError("require competition, event and venue revisions")
        targets = (
            self.competition.competition_id,
            self.event.event_id,
            *(v.venue_id for v in self.venues),
        )
        for row, target in zip(self.revisions, targets, strict=True):
            instance(row, ProviderMappingRevision, "revision")
            if row.canonical_entity_id != target:
                raise ValueError("mapping target does not match reference")
            if row.status is not MappingStatus.MAPPED or row.available_at > self.as_of:
                raise ValueError("mapping must be active and available at cutoff")
            if row.key.data_source_id != self.source.data_source_id:
                raise ValueError("mapping source does not match reference")
        OddsReferenceKeys(
            competition=self.revisions[0].key,
            event=self.revisions[1].key,
            venues=tuple(row.key for row in self.revisions[2:]),
        )


class OddsReferenceResolver(Protocol):
    def resolve(self, keys: OddsReferenceKeys, *, as_of: datetime) -> ResolvedOddsReferences: ...


OddsReferenceReads = Callable[[], AbstractContextManager[OddsReferenceResolver]]
_Id = TypeVar("_Id", CompetitionId, EventId, VenueId)
_Record = TypeVar("_Record", Competition, Event, Venue)


def _read(
    key: ProviderEntityKey,
    mappings: MappingRepository,
    cutoff: datetime,
    expected: type[_Id],
    get: Callable[[_Id], _Record | None],
) -> tuple[ProviderMappingRevision, _Record]:
    row = resolve_mapping(key, mappings.history(key), as_of=cutoff)
    if row is None:
        raise ValueError("reference mapping is missing, revoked, or not yet available")
    if not isinstance(row.canonical_entity_id, expected):
        raise ValueError("reference mapping has the wrong canonical target type")
    record = get(row.canonical_entity_id)
    if record is None:
        raise ValueError("mapped canonical reference is missing")
    return row, record


def resolve_odds_references(
    keys: OddsReferenceKeys,
    mappings: MappingRepository,
    sports: SportsRepository,
    sources: DataSourceRepository,
    venues: VenueRepository,
    *,
    as_of: datetime,
) -> ResolvedOddsReferences:
    """Caller supplies all repositories from one pinned read-only snapshot.

    No I/O outside these reads, implicit inserts, retries or provider name matching.
    A selected mapping cutoff does not make quote availability known.
    """
    instance(keys, OddsReferenceKeys, "keys")
    aware_datetime(as_of, "as_of")
    cutoff = as_of.astimezone(UTC)
    source = sources.get(keys.event.data_source_id)
    if source is None:
        raise ValueError("source reference is missing")
    cr, competition = _read(
        keys.competition, mappings, cutoff, CompetitionId, sports.get_competition
    )
    er, event = _read(keys.event, mappings, cutoff, EventId, sports.get_event)
    sport = sports.get_sport(event.sport_id)
    season = sports.get_season(event.season_id)
    if sport is None or season is None:
        raise ValueError("event hierarchy reference is missing")
    entries = tuple(sports.get_event_participants(event.event_id))
    if len(entries) != 2 or {e.role for e in entries} != {"HOME", "AWAY"}:
        raise ValueError("require exact HOME/AWAY participant roles")
    ordered_entries = tuple(sorted(entries, key=lambda e: e.role != "HOME"))
    home = sports.get_participant(ordered_entries[0].participant_id)
    away = sports.get_participant(ordered_entries[1].participant_id)
    if home is None or away is None:
        raise ValueError("event participant reference is missing")
    venue_rows = tuple(_read(key, mappings, cutoff, VenueId, venues.get) for key in keys.venues)
    return ResolvedOddsReferences(
        source=source,
        sport=sport,
        competition=competition,
        season=season,
        event=event,
        home=home,
        away=away,
        entries=ordered_entries,
        venues=tuple(v for _, v in venue_rows),
        revisions=(cr, er, *(r for r, _ in venue_rows)),
        as_of=cutoff,
    )
