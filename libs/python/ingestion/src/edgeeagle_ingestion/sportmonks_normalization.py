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


def _project(
    manifest: SportmonksCaptureManifest,
    native: NativeSportmonksFixture,
    references: ResolvedSportmonksReferences,
    *,
    parser_version: str = PARSER_VERSION,
    normalizer_version: str = NORMALIZER_VERSION,
    as_of: datetime | None = None,
) -> NormalizedSportmonksFixture:
    """Apply the one canonical projection contract to fresh and retained evidence."""
    instance(manifest, SportmonksCaptureManifest, "manifest")
    instance(native, NativeSportmonksFixture, "native")
    instance(references, ResolvedSportmonksReferences, "references")
    if parser_version != PARSER_VERSION or normalizer_version != NORMALIZER_VERSION:
        raise ValueError("unsupported Sportmonks transformation versions")
    if native.fixture_id != manifest.fixture_id:
        raise ValueError("native fixture differs from capture manifest")
    if native.starts_at <= manifest.snapshot_at:
        raise ValueError("capture snapshot must precede scheduled kickoff")
    cutoff = references.as_of
    aware_datetime(cutoff, "reference cutoff")
    cutoff = cutoff.astimezone(UTC)
    if as_of is not None:
        aware_datetime(as_of, "as_of")
        if as_of.astimezone(UTC) != cutoff:
            raise ValueError("reference evidence differs from requested cutoff")
    keys = _keys(manifest, native)
    if tuple(row.key for row in references.revisions) != keys.ordered():
        raise ValueError("reference evidence differs from requested keys")
    if (
        references.event.status != "SCHEDULED"
        or references.event.starts_at.astimezone(UTC) != native.starts_at
    ):
        raise ValueError("canonical scheduled status or kickoff differs from native fixture")
    season = references.context.season
    if not season.starts_at.astimezone(UTC) <= native.starts_at <= season.ends_at.astimezone(UTC):
        raise ValueError("fixture kickoff falls outside the canonical season")
    return NormalizedSportmonksFixture(
        manifest=manifest,
        native=native,
        references=references,
        parser_version=parser_version,
        normalizer_version=normalizer_version,
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
    return _project(manifest, native, refs, as_of=cutoff)
