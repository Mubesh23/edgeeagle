"""Sport-neutral reference records; not persistence models or historical snapshots."""

from dataclasses import dataclass
from datetime import UTC, datetime

from edgeeagle_domain._validation import aware_datetime, instance, text


@dataclass(frozen=True)
class SportId:
    """Opaque internally allocated sport identity."""

    value: str

    def __post_init__(self) -> None:
        text(self.value, "sport_id")


@dataclass(frozen=True)
class CompetitionId:
    """Opaque internally allocated competition identity."""

    value: str

    def __post_init__(self) -> None:
        text(self.value, "competition_id")


@dataclass(frozen=True)
class SeasonId:
    """Opaque internally allocated season identity."""

    value: str

    def __post_init__(self) -> None:
        text(self.value, "season_id")


@dataclass(frozen=True)
class ParticipantId:
    """Opaque internally allocated participant identity."""

    value: str

    def __post_init__(self) -> None:
        text(self.value, "participant_id")


@dataclass(frozen=True)
class EventId:
    """Opaque internally allocated event identity."""

    value: str

    def __post_init__(self) -> None:
        text(self.value, "event_id")


@dataclass(frozen=True, kw_only=True)
class Sport:
    """Canonical Sport fields; labels do not imply lifecycle or settlement rules."""

    sport_id: SportId
    code: str
    name: str

    def __post_init__(self) -> None:
        instance(self.sport_id, SportId, "sport_id")
        text(self.code, "code")
        text(self.name, "name")


@dataclass(frozen=True, kw_only=True)
class Competition:
    """Canonical Competition fields; labels do not imply lifecycle or settlement rules."""

    competition_id: CompetitionId
    sport_id: SportId
    name: str
    country_or_region: str
    gender_or_division: str | None = None

    def __post_init__(self) -> None:
        instance(self.competition_id, CompetitionId, "competition_id")
        instance(self.sport_id, SportId, "sport_id")
        text(self.name, "name")
        text(self.country_or_region, "country_or_region")
        if self.gender_or_division is not None:
            text(self.gender_or_division, "gender_or_division")


@dataclass(frozen=True, kw_only=True)
class Season:
    """Canonical Season fields; labels do not imply lifecycle or settlement rules."""

    season_id: SeasonId
    competition_id: CompetitionId
    name: str
    starts_at: datetime
    ends_at: datetime

    def __post_init__(self) -> None:
        instance(self.season_id, SeasonId, "season_id")
        instance(self.competition_id, CompetitionId, "competition_id")
        text(self.name, "name")
        aware_datetime(self.starts_at, "starts_at")
        aware_datetime(self.ends_at, "ends_at")
        if self.ends_at.astimezone(UTC) < self.starts_at.astimezone(UTC):
            raise ValueError("ends_at must not precede starts_at")


@dataclass(frozen=True, kw_only=True)
class Participant:
    """Canonical Participant fields; labels do not imply lifecycle or settlement rules."""

    participant_id: ParticipantId
    sport_id: SportId
    participant_type: str
    canonical_name: str

    def __post_init__(self) -> None:
        instance(self.participant_id, ParticipantId, "participant_id")
        instance(self.sport_id, SportId, "sport_id")
        text(self.participant_type, "participant_type")
        text(self.canonical_name, "canonical_name")


@dataclass(frozen=True, kw_only=True)
class Event:
    """Canonical Event fields; labels do not imply lifecycle or settlement rules."""

    event_id: EventId
    sport_id: SportId
    competition_id: CompetitionId
    season_id: SeasonId
    starts_at: datetime
    status: str
    venue_location: str | None = None

    def __post_init__(self) -> None:
        instance(self.event_id, EventId, "event_id")
        instance(self.sport_id, SportId, "sport_id")
        instance(self.competition_id, CompetitionId, "competition_id")
        instance(self.season_id, SeasonId, "season_id")
        aware_datetime(self.starts_at, "starts_at")
        text(self.status, "status")
        if self.venue_location is not None:
            text(self.venue_location, "venue_location")


@dataclass(frozen=True, kw_only=True)
class EventParticipant:
    """Canonical EventParticipant fields; labels do not imply lifecycle or settlement rules."""

    event_id: EventId
    participant_id: ParticipantId
    role: str

    def __post_init__(self) -> None:
        instance(self.event_id, EventId, "event_id")
        instance(self.participant_id, ParticipantId, "participant_id")
        text(self.role, "role")
