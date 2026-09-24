"""Canonical in-memory Odds API projection and replay; no acceptance writes."""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum

from edgeeagle_domain._validation import aware_datetime, instance
from edgeeagle_domain.mappings import ProviderEntityKey
from edgeeagle_domain.markets import (
    Market,
    MarketType,
    Outcome,
    Quote,
    QuoteId,
    Selection,
    validate_market_selections,
)
from edgeeagle_domain.raw import RawPayloadStore

from .odds_api_parser import MAX_EVENTS, PARSER_VERSION, NativeOddsEvent
from .odds_guards import OddsEventGuard, validate_odds_event_guard
from .odds_manifest import OddsCaptureManifest, read_odds_capture
from .odds_references import OddsReferenceKeys, OddsReferenceReads, ResolvedOddsReferences

NORMALIZER_VERSION = "the-odds-api-soccer-h2h-normalization-v1"


@dataclass(frozen=True, kw_only=True)
class OddsEventEvidence:
    guard: OddsEventGuard
    references: ResolvedOddsReferences

    def __post_init__(self) -> None:
        instance(self.guard, OddsEventGuard, "guard")
        instance(self.references, ResolvedOddsReferences, "references")


@dataclass(frozen=True, kw_only=True)
class OddsObservation:
    """Derived projection, not a validated persistence command or executable offer."""

    provider_event_id: str
    bookmaker_key: str
    market: Market
    selections: tuple[Selection, ...]
    quotes: tuple[Quote, ...]
    bookmaker_updated_at: datetime | None
    market_updated_at: datetime | None


@dataclass(frozen=True, kw_only=True)
class NormalizedOddsCapture:
    """Retain empty captures too. Receipt serialization is a separate increment."""

    manifest: OddsCaptureManifest
    evidence: tuple[OddsEventEvidence, ...]
    observations: tuple[OddsObservation, ...]
    parser_version: str = PARSER_VERSION
    normalizer_version: str = NORMALIZER_VERSION


def _scalar(value: object) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Enum):
        return str(value.value)
    raise TypeError("unsupported odds identity scalar")


def _identity_seed(manifest: OddsCaptureManifest) -> str:
    # No derived price/context in identity: changed projections must conflict on
    # retry, not silently create a second observation after mapping correction.
    value = {
        "identity_version": 1,
        "manifest": asdict(manifest),
        "parser_version": PARSER_VERSION,
        "normalizer_version": NORMALIZER_VERSION,
    }
    body = json.dumps(
        value, default=_scalar, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(body.encode("ascii")).hexdigest()


def _keys(manifest: OddsCaptureManifest, event: NativeOddsEvent) -> OddsReferenceKeys:
    def key(kind: str, identity: str) -> ProviderEntityKey:
        return ProviderEntityKey(
            data_source_id=manifest.raw.capture.data_source_id,
            provider_entity_type=kind,
            provider_entity_id=identity,
        )

    return OddsReferenceKeys(
        competition=key("competition", manifest.sport_key),
        event=key("event", event.event_id),
        venues=tuple(key("bookmaker", book.bookmaker_key) for book in event.bookmakers),
    )


def _project(
    events: tuple[NativeOddsEvent, ...],
    manifest: OddsCaptureManifest,
    evidence: tuple[OddsEventEvidence, ...],
) -> NormalizedOddsCapture:
    instance(evidence, tuple, "evidence")
    if len(evidence) != len(events):
        raise ValueError("require exact whole-capture event evidence")
    seen_events = set()
    observations = []
    seed = _identity_seed(manifest)
    profiles = {p.bookmaker_key: p for p in manifest.settlement_profiles}
    cutoffs = set()
    for native, retained in zip(events, evidence, strict=True):
        instance(retained, OddsEventEvidence, "event evidence")
        refs, guard = retained.references, retained.guard
        validate_odds_event_guard(guard, native, refs, snapshot_at=manifest.snapshot_at)
        keys = _keys(manifest, native)
        if tuple(row.key for row in refs.revisions) != keys.ordered():
            raise ValueError("reference evidence differs from requested source/event/bookmakers")
        if refs.event.event_id in seen_events:
            raise ValueError("provider events collapse to one canonical event")
        seen_events.add(refs.event.event_id)
        cutoffs.add(refs.as_of)
        for book, venue in zip(native.bookmakers, refs.venues, strict=True):
            if not book.outcomes:
                continue
            market = Market(
                event_id=refs.event.event_id,
                market_type=MarketType.RESULT_3WAY,
                period=profiles[book.bookmaker_key].period,
            )
            roles = {
                guard.home_label: (Outcome.HOME, guard.home_id),
                "Draw": (Outcome.DRAW, None),
                guard.away_label: (Outcome.AWAY, guard.away_id),
            }
            selections, quotes = [], []
            for outcome in book.outcomes:
                role, participant = roles[outcome.name]
                selection = Selection(
                    market_id=market.market_id, outcome=role, participant_id=participant
                )
                identity = json.dumps(
                    [seed, native.event_id, book.bookmaker_key, role.value], separators=(",", ":")
                )
                quote = Quote(
                    quote_id=QuoteId(hashlib.sha256(identity.encode()).hexdigest()),
                    selection_id=selection.selection_id,
                    data_source_id=refs.source.data_source_id,
                    venue_id=venue.venue_id,
                    odds_decimal=outcome.price,
                    ingested_at=manifest.raw.capture.ingested_at,
                    observed_at=book.market_updated_at,
                )
                selections.append(selection)
                quotes.append(quote)
            ordered_selections = tuple(sorted(selections, key=lambda s: s.selection_id.value))
            validate_market_selections(market, ordered_selections, refs.entries)
            observations.append(
                OddsObservation(
                    provider_event_id=native.event_id,
                    bookmaker_key=book.bookmaker_key,
                    market=market,
                    selections=ordered_selections,
                    quotes=tuple(sorted(quotes, key=lambda q: q.quote_id.value)),
                    bookmaker_updated_at=book.bookmaker_updated_at,
                    market_updated_at=book.market_updated_at,
                )
            )
    if len(cutoffs) > 1:
        raise ValueError("capture evidence must share one mapping cutoff")
    return NormalizedOddsCapture(
        manifest=manifest, evidence=evidence, observations=tuple(observations)
    )


def normalize_odds_capture(
    store: RawPayloadStore,
    manifest: OddsCaptureManifest,
    guards: tuple[OddsEventGuard, ...],
    reads: OddsReferenceReads,
    *,
    as_of: datetime,
) -> NormalizedOddsCapture:
    """Validate raw first, resolve all context in one read snapshot, then project.

    No raw-store I/O occurs inside the reference transaction. Nothing is written,
    and partial captures are never returned. The caller owns the read composition.
    """
    instance(manifest, OddsCaptureManifest, "manifest")
    aware_datetime(as_of, "as_of")
    cutoff = as_of.astimezone(UTC)
    instance(guards, tuple, "guards")
    if len(guards) > MAX_EVENTS:
        raise ValueError("too many event guards")
    for guard in guards:
        instance(guard, OddsEventGuard, "guard")
        if guard.event_key.data_source_id != manifest.raw.capture.data_source_id:
            raise ValueError("guard source differs from capture")
    by_id = {guard.event_key.provider_entity_id: guard for guard in guards}
    if len(by_id) != len(guards):
        raise ValueError("duplicate event guards")
    events = read_odds_capture(store, manifest)
    if set(by_id) != {event.event_id for event in events}:
        raise ValueError("require exact whole-capture event guards")
    retained = []
    if events:
        with reads() as resolver:
            for event in events:
                refs = resolver.resolve(_keys(manifest, event), as_of=cutoff)
                if refs.as_of != cutoff:
                    raise ValueError("resolver returned the wrong cutoff")
                retained.append(OddsEventEvidence(guard=by_id[event.event_id], references=refs))
    return _project(events, manifest, tuple(retained))


def replay_odds_capture(store: RawPayloadStore, capture: NormalizedOddsCapture) -> None:
    """Compare the full derived projection using retained context, never current mappings."""
    instance(capture, NormalizedOddsCapture, "capture")
    if capture.parser_version != PARSER_VERSION or capture.normalizer_version != NORMALIZER_VERSION:
        raise ValueError("unsupported odds replay version")
    events = read_odds_capture(store, capture.manifest)
    if _project(events, capture.manifest, capture.evidence) != capture:
        raise ValueError("odds replay differs from retained projection")
