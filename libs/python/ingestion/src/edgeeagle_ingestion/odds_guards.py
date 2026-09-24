"""Exact, explicitly supplied Odds API event guards; never infer identity from names."""

from dataclasses import dataclass
from datetime import UTC, datetime

from edgeeagle_domain._validation import aware_datetime, instance
from edgeeagle_domain.mappings import ProviderEntityKey
from edgeeagle_domain.sports import ParticipantId

from .odds_api_parser import NativeOddsEvent
from .odds_references import ResolvedOddsReferences


def _label(value: str) -> None:
    if (
        not isinstance(value, str)
        or not 1 <= len(value) <= 256
        or value != value.strip()
        or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value)
    ):
        raise ValueError("require a bounded exact provider label")


@dataclass(frozen=True, kw_only=True)
class OddsEventGuard:
    """Retain the declared label-to-canonical-role association and kickoff.

    Labels are comparison guards, not participant identifiers or evidence of
    human approval. These values alone grant no capture rights or eligibility.
    """

    event_key: ProviderEntityKey
    home_id: ParticipantId
    away_id: ParticipantId
    home_label: str
    away_label: str
    starts_at: datetime

    def __post_init__(self) -> None:
        instance(self.event_key, ProviderEntityKey, "event_key")
        instance(self.home_id, ParticipantId, "home_id")
        instance(self.away_id, ParticipantId, "away_id")
        if self.event_key.provider_entity_type != "event":
            raise ValueError("require a provider event key")
        if self.home_id == self.away_id:
            raise ValueError("require distinct canonical participants")
        _label(self.home_label)
        _label(self.away_label)
        if len({self.home_label, self.away_label, "Draw"}) != 3:
            raise ValueError("require distinct HOME/DRAW/AWAY labels")
        aware_datetime(self.starts_at, "starts_at")
        object.__setattr__(self, "starts_at", self.starts_at.astimezone(UTC))


def validate_odds_event_guard(
    guard: OddsEventGuard,
    native: NativeOddsEvent,
    references: ResolvedOddsReferences,
    *,
    snapshot_at: datetime,
) -> None:
    """Check parsed native context against explicit guards and pinned references.

    Pure validation only: no current mapping reads, canonical updates or fuzzy
    matching. The caller must still validate the full capture, settlement profile,
    raw integrity and provenance before producing observations.
    """
    instance(guard, OddsEventGuard, "guard")
    instance(native, NativeOddsEvent, "native")
    instance(references, ResolvedOddsReferences, "references")
    aware_datetime(snapshot_at, "snapshot_at")
    aware_datetime(native.commence_time, "commence_time")
    competition_key, event_key = (r.key for r in references.revisions[:2])
    if (
        competition_key.provider_entity_type != "competition"
        or event_key != guard.event_key
        or native.event_id != event_key.provider_entity_id
        or native.sport_key != competition_key.provider_entity_id
    ):
        raise ValueError("provider event/competition does not match pinned references")
    if (guard.home_id, guard.away_id) != (
        references.home.participant_id,
        references.away.participant_id,
    ):
        raise ValueError("guard participants do not match canonical HOME/AWAY roles")
    if (native.home_team, native.away_team) != (guard.home_label, guard.away_label):
        raise ValueError("provider labels differ from exact guards")
    if not native.commence_time == guard.starts_at == references.event.starts_at:
        raise ValueError("provider, guard and canonical kickoff must agree")
    if guard.starts_at <= snapshot_at:
        raise ValueError("capture must be strictly pre-match")
