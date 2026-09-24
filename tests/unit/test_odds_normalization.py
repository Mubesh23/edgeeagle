import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal, localcontext
from pathlib import Path
from unittest.mock import Mock

import pytest

from edgeeagle_domain.markets import Outcome
from edgeeagle_domain.provenance import VenueId
from edgeeagle_domain.raw import RawPayload
from edgeeagle_domain.sports import EventId
from edgeeagle_ingestion.odds_guards import OddsEventGuard
from edgeeagle_ingestion.odds_manifest import OddsCaptureManifest
from edgeeagle_ingestion.odds_normalization import normalize_odds_capture, replay_odds_capture
from edgeeagle_ingestion.odds_references import (
    OddsReferenceReads,
    OddsReferenceResolver,
    ResolvedOddsReferences,
    resolve_odds_references,
)
from tests.unit.test_odds_manifest import NOW, manifest
from tests.unit.test_odds_references import setup_references


def inputs() -> tuple[
    OddsCaptureManifest, OddsEventGuard, ResolvedOddsReferences, Mock, Mock, OddsReferenceReads
]:
    body = Path("tests/fixtures/providers/the_odds_api/pre-match-v1/odds-success.json").read_bytes()
    refs = resolve_odds_references(*setup_references(), as_of=NOW)
    event_key = replace(refs.revisions[1].key, provider_entity_id="authored-odds-api-event-001")
    refs = replace(
        refs,
        revisions=(
            refs.revisions[0],
            replace(refs.revisions[1], key=event_key),
            *refs.revisions[2:],
        ),
    )
    guard = OddsEventGuard(
        event_key=event_key,
        home_id=refs.home.participant_id,
        away_id=refs.away.participant_id,
        home_label="Authored Home FC",
        away_label="Authored Away FC",
        starts_at=refs.event.starts_at,
    )
    m = manifest()
    m = replace(
        m,
        raw=RawPayload(
            capture=replace(m.raw.capture, data_source_id=refs.source.data_source_id), body=body
        ).reference(),
    )
    store, resolver = Mock(), Mock()
    store.get.return_value = body
    resolver.resolve.return_value = refs
    active = False

    @contextmanager
    def reads() -> Iterator[OddsReferenceResolver]:
        nonlocal active
        assert not active
        store.get.assert_called_once_with(m.raw)
        active = True
        try:
            yield resolver
        finally:
            active = False

    return m, guard, refs, store, resolver, reads


def test_exact_prices_canonical_roles_and_scoped_timestamps() -> None:
    m, guard, refs, store, resolver, reads = inputs()
    with localcontext() as context:
        context.prec = 4
        batch = normalize_odds_capture(store, m, (guard,), reads, as_of=NOW)
    assert batch.manifest == m
    assert batch.evidence[0].references == refs
    assert len(batch.observations) == 1
    observation = batch.observations[0]
    assert observation.market.event_id == refs.event.event_id
    assert {s.outcome: s.participant_id for s in observation.selections} == {
        Outcome.HOME: refs.home.participant_id,
        Outcome.DRAW: None,
        Outcome.AWAY: refs.away.participant_id,
    }
    assert {q.odds_decimal for q in observation.quotes} == {
        Decimal("2.12345678901234567890123456789"),
        Decimal("3.2"),
        Decimal("3.4"),
    }
    assert observation.bookmaker_updated_at == NOW - timedelta(minutes=1)
    assert observation.market_updated_at is None
    assert all(
        q.observed_at is None and q.available_at is None and q.effective_at is None
        for q in observation.quotes
    )
    assert all(
        q.data_source_id == refs.source.data_source_id and q.venue_id == refs.venues[0].venue_id
        for q in observation.quotes
    )
    resolver.resolve.assert_called_once()
    store.put.assert_not_called()
    resolver.resolve.side_effect = AssertionError("replay must not consult mappings")
    replay_odds_capture(store, batch)


@pytest.mark.parametrize("empty", ["events", "books", "markets"])
def test_zero_observations_retain_manifest_and_event_evidence(empty: str) -> None:
    m, guard, refs, store, resolver, _ = inputs()
    rows = json.loads(store.get.return_value)
    guards: tuple[OddsEventGuard, ...]
    if empty == "events":
        rows = []
        guards = ()
    else:
        guards = (guard,)
        if empty == "books":
            rows[0]["bookmakers"] = []
            refs = replace(refs, venues=(), revisions=refs.revisions[:2])
        else:
            rows[0]["bookmakers"][0]["markets"] = []
    body = json.dumps(rows).encode()
    m = replace(m, raw=RawPayload(capture=m.raw.capture, body=body).reference())
    store.get.return_value = body
    resolver.resolve.return_value = refs

    @contextmanager
    def reads() -> Iterator[OddsReferenceResolver]:
        yield resolver

    batch = normalize_odds_capture(store, m, guards, reads, as_of=NOW)
    assert batch.observations == ()
    assert batch.manifest == m
    assert len(batch.evidence) == len(guards)
    replay_odds_capture(store, batch)


@pytest.mark.parametrize(
    "failure", ["missing", "extra", "duplicate", "labels", "source", "cutoff", "books"]
)
def test_inconsistent_capture_context_fails_whole_normalization(failure: str) -> None:
    m, guard, refs, store, resolver, reads = inputs()
    guards: tuple[OddsEventGuard, ...] = (guard,)
    if failure == "missing":
        guards = ()
    if failure == "extra":
        guards = (
            guard,
            replace(guard, event_key=replace(guard.event_key, provider_entity_id="other")),
        )
    if failure == "duplicate":
        guards = (guard, guard)
    if failure == "labels":
        guards = (replace(guard, home_label="wrong"),)
    if failure == "source":
        m = manifest()
    if failure == "cutoff":
        resolver.resolve.return_value = replace(refs, as_of=NOW + timedelta(seconds=1))
    if failure == "books":
        resolver.resolve.return_value = replace(refs, venues=(), revisions=refs.revisions[:2])
    with pytest.raises(ValueError):
        normalize_odds_capture(store, m, guards, reads, as_of=NOW)
    store.put.assert_not_called()


def test_replay_detects_changed_or_missing_projection() -> None:
    m, guard, _, store, _, reads = inputs()
    batch = normalize_odds_capture(store, m, (guard,), reads, as_of=NOW)
    observation = batch.observations[0]
    for observations in (
        (),
        (
            replace(
                observation,
                quotes=(
                    replace(observation.quotes[0], odds_decimal=Decimal("99")),
                    *observation.quotes[1:],
                ),
            ),
        ),
    ):
        with pytest.raises(ValueError, match="replay"):
            replay_odds_capture(store, replace(batch, observations=observations))


def test_malformed_body_is_rejected_before_any_reference_read() -> None:
    m, guard, _, store, _, _ = inputs()
    body = b"{}"
    m = replace(m, raw=RawPayload(capture=m.raw.capture, body=body).reference())
    store.get.return_value = body
    reads = Mock(side_effect=AssertionError("no reads"))
    with pytest.raises(ValueError):
        normalize_odds_capture(store, m, (guard,), reads, as_of=NOW)
    reads.assert_not_called()


def test_bounds_and_replay_versions_and_missing_evidence() -> None:
    m, guard, _, store, _, reads = inputs()
    with pytest.raises(ValueError, match="too many"):
        normalize_odds_capture(store, m, (guard,) * 101, reads, as_of=NOW)
    batch = normalize_odds_capture(store, m, (guard,), reads, as_of=NOW)
    for changed in (
        replace(batch, parser_version="future"),
        replace(batch, normalizer_version="future"),
        replace(batch, evidence=()),
    ):
        with pytest.raises(ValueError):
            replay_odds_capture(store, changed)


def test_mapping_correction_changes_projection_not_observation_identity() -> None:
    m, guard, refs, store, resolver, reads = inputs()
    original = normalize_odds_capture(store, m, (guard,), reads, as_of=NOW)
    venue = replace(refs.venues[0], venue_id=VenueId("corrected"))
    resolver.resolve.return_value = replace(
        refs,
        venues=(venue,),
        revisions=(
            *refs.revisions[:2],
            replace(refs.revisions[2], canonical_entity_id=venue.venue_id),
        ),
    )
    store.get.reset_mock()
    corrected = normalize_odds_capture(store, m, (guard,), reads, as_of=NOW)
    assert [q.quote_id for q in original.observations[0].quotes] == [
        q.quote_id for q in corrected.observations[0].quotes
    ]
    assert original != corrected
    resolver.resolve.side_effect = ValueError("revoked")
    replay_odds_capture(store, original)
    store.get.reset_mock()
    with pytest.raises(ValueError, match="revoked"):
        normalize_odds_capture(store, m, (guard,), reads, as_of=NOW)


def test_multiple_events_share_one_snapshot_and_reject_collapsed_or_mixed_evidence() -> None:
    m, guard, refs, store, resolver, _ = inputs()
    row = json.loads(store.get.return_value)[0]
    body = json.dumps([dict(row, id="second"), row]).encode()
    m = replace(m, raw=RawPayload(capture=m.raw.capture, body=body).reference())
    store.get.return_value = body
    second_guard = replace(guard, event_key=replace(guard.event_key, provider_entity_id="second"))
    event_id = EventId("second-canonical")
    second_refs = replace(
        refs,
        event=replace(refs.event, event_id=event_id),
        entries=tuple(replace(e, event_id=event_id) for e in refs.entries),
        revisions=(
            refs.revisions[0],
            replace(refs.revisions[1], key=second_guard.event_key, canonical_entity_id=event_id),
            *refs.revisions[2:],
        ),
    )
    resolver.resolve.side_effect = [refs, second_refs]
    openings = []

    @contextmanager
    def reads() -> Iterator[OddsReferenceResolver]:
        store.get.assert_called_once_with(m.raw)
        openings.append("open")
        yield resolver

    batch = normalize_odds_capture(store, m, (second_guard, guard), reads, as_of=NOW)
    assert len(openings) == 1 and len(batch.observations) == 2
    assert len({q.quote_id for o in batch.observations for q in o.quotes}) == 6
    replay_odds_capture(store, batch)
    mixed = replace(
        batch.evidence[1], references=replace(second_refs, as_of=NOW + timedelta(seconds=1))
    )
    with pytest.raises(ValueError, match="cutoff"):
        replay_odds_capture(store, replace(batch, evidence=(batch.evidence[0], mixed)))
    collapsed = replace(
        refs,
        revisions=(
            refs.revisions[0],
            replace(refs.revisions[1], key=second_guard.event_key),
            *refs.revisions[2:],
        ),
    )
    with pytest.raises(ValueError, match="collapse"):
        replay_odds_capture(
            store,
            replace(
                batch,
                evidence=(batch.evidence[0], replace(batch.evidence[1], references=collapsed)),
            ),
        )


def test_market_update_is_not_inferred_from_bookmaker_or_raw_timestamps() -> None:
    m, guard, _, store, resolver, _ = inputs()
    rows = json.loads(store.get.return_value)
    rows[0]["bookmakers"][0]["markets"][0]["last_update"] = "2026-09-23T11:58:00Z"
    body = json.dumps(rows).encode()
    m = replace(
        m,
        raw=RawPayload(
            capture=replace(m.raw.capture, observed_at=NOW, effective_at=NOW), body=body
        ).reference(),
    )
    store.get.return_value = body

    @contextmanager
    def reads() -> Iterator[OddsReferenceResolver]:
        yield resolver

    batch = normalize_odds_capture(store, m, (guard,), reads, as_of=NOW)
    observation = batch.observations[0]
    assert observation.bookmaker_updated_at == NOW - timedelta(minutes=1)
    assert observation.market_updated_at == NOW - timedelta(minutes=2)
    assert all(
        q.observed_at == observation.market_updated_at
        and q.effective_at is None
        and q.available_at is None
        for q in observation.quotes
    )
