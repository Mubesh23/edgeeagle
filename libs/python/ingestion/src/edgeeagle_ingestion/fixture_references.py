"""Read-only fixture reference resolution; mapped receipt wiring is separate (ADR-025)."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, TypeVar

from edgeeagle_domain._validation import aware_datetime, instance
from edgeeagle_domain.mapping_repository import MappingRepository
from edgeeagle_domain.mappings import (
    MappingStatus,
    ProviderEntityKey,
    ProviderMappingRevision,
    resolve_mapping,
)
from edgeeagle_domain.sports import (
    Competition,
    CompetitionId,
    Participant,
    ParticipantId,
    Season,
    SeasonId,
    Sport,
    SportId,
)
from edgeeagle_domain.sports_repository import SportsRepository


@dataclass(frozen=True, kw_only=True)
class FixtureReferenceKeys:
    """Authored manifest identities, never inferred from display labels."""

    sport: ProviderEntityKey
    competition: ProviderEntityKey
    season: ProviderEntityKey
    home: ProviderEntityKey
    away: ProviderEntityKey

    def ordered(self) -> tuple[ProviderEntityKey, ...]:
        return self.sport, self.competition, self.season, self.home, self.away

    def __post_init__(self) -> None:
        for key in self.ordered():
            instance(key, ProviderEntityKey, "reference key")
        if len(set(self.ordered())) != 5:
            raise ValueError("reference keys must be distinct")
        if len({key.data_source_id for key in self.ordered()}) != 1:
            raise ValueError("reference keys must share a source")


class FixtureReferenceResolver(Protocol):
    def resolve(
        self, keys: FixtureReferenceKeys, *, as_of: datetime
    ) -> "ResolvedFixtureReferences": ...


FixtureReferenceReads = Callable[[], AbstractContextManager[FixtureReferenceResolver]]


@dataclass(frozen=True, kw_only=True)
class ResolvedFixtureReferences:
    """Selected records and evidence, not a persisted or historical snapshot.

    Revisions are ordered sport, competition, season, home, away. Retain this
    evidence; do not drop it to persist through the legacy format-1 path.
    """

    sport: Sport
    competition: Competition
    season: Season
    home: Participant
    away: Participant
    revisions: tuple[ProviderMappingRevision, ...]
    as_of: datetime

    def __post_init__(self) -> None:
        aware_datetime(self.as_of, "as_of")
        for record, expected in (
            (self.sport, Sport),
            (self.competition, Competition),
            (self.season, Season),
            (self.home, Participant),
            (self.away, Participant),
        ):
            instance(record, expected, "reference record")
        instance(self.revisions, tuple, "revisions")
        if len(self.revisions) != 5:
            raise ValueError("require five role-specific revisions")
        targets = (
            self.sport.sport_id,
            self.competition.competition_id,
            self.season.season_id,
            self.home.participant_id,
            self.away.participant_id,
        )
        for row, target in zip(self.revisions, targets, strict=True):
            instance(row, ProviderMappingRevision, "revision")
            if row.canonical_entity_id != target:
                raise ValueError("mapping target does not match reference record")
            if row.status is not MappingStatus.MAPPED or row.available_at > self.as_of:
                raise ValueError("mapping must be active and available at cutoff")
        FixtureReferenceKeys(
            **dict(
                zip(
                    ("sport", "competition", "season", "home", "away"),
                    (row.key for row in self.revisions),
                    strict=True,
                )
            )
        )
        if self.competition.sport_id != self.sport.sport_id:
            raise ValueError("competition and sport mismatch")
        if self.season.competition_id != self.competition.competition_id:
            raise ValueError("season and competition mismatch")
        if any(p.sport_id != self.sport.sport_id for p in (self.home, self.away)):
            raise ValueError("participant and sport mismatch")
        if self.home.participant_id == self.away.participant_id:
            raise ValueError("home and away must be distinct participants")


_Id = TypeVar("_Id", SportId, CompetitionId, SeasonId, ParticipantId)
_Record = TypeVar("_Record", Sport, Competition, Season, Participant)


def _read(
    key: ProviderEntityKey,
    mappings: MappingRepository,
    as_of: datetime,
    expected: type[_Id],
    get: Callable[[_Id], _Record | None],
) -> tuple[ProviderMappingRevision, _Record]:
    row = resolve_mapping(key, mappings.history(key), as_of=as_of)
    if row is None:
        raise ValueError("reference mapping is missing, revoked, or not yet available")
    if not isinstance(row.canonical_entity_id, expected):
        raise ValueError("reference mapping has the wrong canonical target type")
    record = get(row.canonical_entity_id)
    if record is None:
        raise ValueError("mapped canonical reference is missing")
    return row, record


def resolve_fixture_references(
    keys: FixtureReferenceKeys,
    mappings: MappingRepository,
    sports: SportsRepository,
    *,
    as_of: datetime,
) -> ResolvedFixtureReferences:
    """Caller must supply both repositories from one pinned read-only snapshot.

    This port-level operation cannot enforce isolation. It writes nothing, never
    resolves/creates an event, and propagates repository failures without retry.
    """
    instance(keys, FixtureReferenceKeys, "keys")
    aware_datetime(as_of, "as_of")
    cutoff = as_of.astimezone(UTC)
    sr, sport = _read(keys.sport, mappings, cutoff, SportId, sports.get_sport)
    cr, competition = _read(
        keys.competition, mappings, cutoff, CompetitionId, sports.get_competition
    )
    yr, season = _read(keys.season, mappings, cutoff, SeasonId, sports.get_season)
    hr, home = _read(keys.home, mappings, cutoff, ParticipantId, sports.get_participant)
    ar, away = _read(keys.away, mappings, cutoff, ParticipantId, sports.get_participant)
    return ResolvedFixtureReferences(
        sport=sport,
        competition=competition,
        season=season,
        home=home,
        away=away,
        revisions=(sr, cr, yr, hr, ar),
        as_of=cutoff,
    )
