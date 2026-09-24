"""Canonical-linked Sportmonks staging; no receipt or acceptance writes."""

from dataclasses import dataclass
from datetime import UTC, datetime

from edgeeagle_domain._validation import aware_datetime, instance
from edgeeagle_domain.mappings import ProviderEntityKey
from edgeeagle_domain.raw import RawPayloadStore

from .fixture_references import FixtureReferenceKeys
from .sportmonks_manifest import SportmonksCaptureManifest, read_sportmonks_capture
from .sportmonks_parser import PARSER_VERSION, NativeSportmonksFixture
from .sportmonks_references import (
    ResolvedSportmonksReferences,
    SportmonksReferenceKeys,
    SportmonksReferenceReads,
)

NORMALIZER_VERSION = "sportmonks-scheduled-fixture-mappings-v1"


@dataclass(frozen=True, kw_only=True)
class NormalizedSportmonksFixture:
    """Derived in-memory candidate, not a validated persistence command or receipt.

    Keep manifest, native evidence and selected canonical context together. A later
    acceptance boundary must validate/version durable evidence independently.
    """

    manifest: SportmonksCaptureManifest
    native: NativeSportmonksFixture
    references: ResolvedSportmonksReferences
    parser_version: str = PARSER_VERSION
    normalizer_version: str = NORMALIZER_VERSION


def _keys(
    manifest: SportmonksCaptureManifest, native: NativeSportmonksFixture
) -> SportmonksReferenceKeys:
    def key(kind: str, value: int) -> ProviderEntityKey:
        return ProviderEntityKey(
            data_source_id=manifest.raw.capture.data_source_id,
            provider_entity_type=kind,
            provider_entity_id=str(value),
        )

    return SportmonksReferenceKeys(
        context=FixtureReferenceKeys(
            sport=key("sport", native.sport_id),
            competition=key("league", native.league_id),
            season=key("season", native.season_id),
            home=key("participant", native.home.participant_id),
            away=key("participant", native.away.participant_id),
        ),
        event=key("fixture", native.fixture_id),
    )


def normalize_sportmonks_capture(
    store: RawPayloadStore,
    manifest: SportmonksCaptureManifest,
    reads: SportmonksReferenceReads,
    *,
    as_of: datetime,
) -> NormalizedSportmonksFixture:
    """Verify raw before opening one reference snapshot; return no partial result.

    Exact kickoff/status agreement is the supported subset, not a rescheduling
    rule. Canonical names need not match provider labels: explicit IDs supply the
    identity evidence. Mapping cutoff never establishes capture availability.
    """
    instance(manifest, SportmonksCaptureManifest, "manifest")
    aware_datetime(as_of, "as_of")
    cutoff = as_of.astimezone(UTC)
    native = read_sportmonks_capture(store, manifest)
    keys = _keys(manifest, native)
    with reads() as resolver:
        refs = resolver.resolve(keys, as_of=cutoff)
    instance(refs, ResolvedSportmonksReferences, "references")
    if refs.as_of != cutoff or tuple(r.key for r in refs.revisions) != keys.ordered():
        raise ValueError("reference evidence differs from requested keys or cutoff")
    if refs.event.status != "SCHEDULED" or refs.event.starts_at.astimezone(UTC) != native.starts_at:
        raise ValueError("canonical scheduled status or kickoff differs from native fixture")
    season = refs.context.season
    if not season.starts_at.astimezone(UTC) <= native.starts_at <= season.ends_at.astimezone(UTC):
        raise ValueError("fixture kickoff falls outside the canonical season")
    return NormalizedSportmonksFixture(manifest=manifest, native=native, references=refs)
