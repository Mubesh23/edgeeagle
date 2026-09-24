from dataclasses import replace
from datetime import timedelta
from unittest.mock import Mock

import pytest

from edgeeagle_domain.mappings import (
    CanonicalEntityId,
    MappingStatus,
    ProviderEntityKey,
    ProviderMappingRevision,
)
from edgeeagle_domain.provenance import DataSourceId, SourceType, VenueId, VenueType
from edgeeagle_domain.sports import Event, EventParticipant, SportId
from edgeeagle_ingestion.odds_references import OddsReferenceKeys, resolve_odds_references
from tests.unit.test_fixture_references import NOW
from tests.unit.test_market_normalization import context


def setup_references() -> tuple[OddsReferenceKeys, Mock, Mock, Mock, Mock]:
    c = context()
    b = c.event
    source = replace(c.source, code="THE_ODDS_API", capabilities=frozenset())
    keys = OddsReferenceKeys(
        competition=ProviderEntityKey(
            data_source_id=source.data_source_id,
            provider_entity_type="competition",
            provider_entity_id="soccer_epl",
        ),
        event=b.key,
        venues=(
            ProviderEntityKey(
                data_source_id=source.data_source_id,
                provider_entity_type="bookmaker",
                provider_entity_id="bovada",
            ),
        ),
    )
    targets: tuple[CanonicalEntityId, ...] = (
        b.competition.competition_id,
        b.event_id,
        c.venues[0].venue.venue_id,
    )
    rows = {
        key: (
            ProviderMappingRevision(
                key=key,
                revision=1,
                canonical_entity_id=target,
                mapping_method="reviewed-fixture",
                confidence=None,
                validated_by="authored-test",
                validated_at=NOW,
                available_at=NOW,
                ingested_at=NOW,
                status=MappingStatus.MAPPED,
            ),
        )
        for key, target in zip(keys.ordered(), targets, strict=True)
    }
    mappings, sports, sources, venues = Mock(), Mock(), Mock(), Mock()
    mappings.history.side_effect = rows.__getitem__
    sources.get.return_value = source
    venues.get.return_value = c.venues[0].venue
    sports.get_sport.return_value = b.sport
    sports.get_competition.return_value = b.competition
    sports.get_season.return_value = b.season
    sports.get_event.return_value = Event(
        event_id=b.event_id,
        sport_id=b.sport.sport_id,
        competition_id=b.competition.competition_id,
        season_id=b.season.season_id,
        starts_at=c.starts_at,
        status=b.status,
    )
    sports.get_event_participants.return_value = tuple(
        EventParticipant(event_id=b.event_id, participant_id=p.participant_id, role=role)
        for p, role in ((b.home, "HOME"), (b.away, "AWAY"))
    )
    sports.get_participant.side_effect = {p.participant_id: p for p in (b.home, b.away)}.get
    return keys, mappings, sports, sources, venues


def test_resolves_existing_context_and_full_mapping_evidence_without_writes() -> None:
    args = setup_references()
    result = resolve_odds_references(*args, as_of=NOW)
    assert tuple(r.key for r in result.revisions) == args[0].ordered()
    assert result.home == context().event.home
    assert result.away == context().event.away
    assert result.source.code == "THE_ODDS_API"
    assert result.as_of == NOW
    for repo in args[1:]:
        assert all(c[0] == "history" or c[0].startswith("get") for c in repo.mock_calls)


@pytest.mark.parametrize("failure", ["missing", "future", "revoked", "gap", "wrong-type"])
def test_mapping_failures(failure: str) -> None:
    args = setup_references()
    keys, mappings, *_ = args
    original = mappings.history.side_effect
    row = original(keys.event)[0]
    future = NOW + timedelta(days=1)
    histories = {
        "missing": (),
        "future": (replace(row, available_at=future, ingested_at=future),),
        "revoked": (row, replace(row, revision=2, status=MappingStatus.REVOKED)),
        "gap": (row, replace(row, revision=3, available_at=future, ingested_at=future)),
        "wrong-type": (replace(row, canonical_entity_id=SportId("s1")),),
    }
    mappings.history.side_effect = lambda key: (
        histories[failure] if key == keys.event else original(key)
    )
    with pytest.raises(ValueError):
        resolve_odds_references(*args, as_of=NOW)


@pytest.mark.parametrize(
    "record", ["source", "venue", "event", "competition", "sport", "season", "participant"]
)
def test_missing_records_fail_closed(record: str) -> None:
    args = setup_references()
    _, _, sports, sources, venues = args
    repo, method = (
        (sources, "get")
        if record == "source"
        else (venues, "get")
        if record == "venue"
        else (sports, f"get_{record}")
    )
    getattr(repo, method).side_effect = None
    getattr(repo, method).return_value = None
    with pytest.raises(ValueError):
        resolve_odds_references(*args, as_of=NOW)


def test_invalid_context_and_evidence() -> None:
    result = resolve_odds_references(*setup_references(), as_of=NOW)
    for changes in (
        {"source": replace(result.source, code="OTHER")},
        {"source": replace(result.source, source_type=SourceType.VENUE_API)},
        {"sport": replace(result.sport, code="basketball")},
        {"home": replace(result.home, participant_type="PERSON")},
        {"entries": (result.entries[0], replace(result.entries[1], role="HOME"))},
        {"revisions": result.revisions[:-1]},
        {"as_of": NOW - timedelta(seconds=1)},
        {"venues": (replace(result.venues[0], venue_id=VenueId("other")),)},
        {"venues": (replace(result.venues[0], venue_type=VenueType.EXCHANGE),)},
        {"venues": result.venues * 2},
        {"source": replace(result.source, data_source_id=DataSourceId("other"))},
        {
            "revisions": (
                replace(result.revisions[0], status=MappingStatus.REVOKED),
                *result.revisions[1:],
            )
        },
    ):
        with pytest.raises(ValueError):
            replace(result, **changes)


def test_empty_venues_are_valid_and_duplicate_keys_are_not() -> None:
    keys, *repos = setup_references()
    assert resolve_odds_references(replace(keys, venues=()), *repos, as_of=NOW).venues == ()
    with pytest.raises(ValueError):
        replace(keys, venues=keys.venues * 2)
    with pytest.raises(ValueError):
        replace(keys, venues=keys.venues * 21)
    with pytest.raises(ValueError):
        replace(keys, event=replace(keys.event, data_source_id=DataSourceId("other")))


def test_bad_roles_and_repository_failures_do_not_fall_back() -> None:
    args = setup_references()
    args[2].get_event_participants.return_value = ()
    with pytest.raises(ValueError, match="HOME/AWAY"):
        resolve_odds_references(*args, as_of=NOW)
    args[1].history.side_effect = OSError("unavailable")
    with pytest.raises(OSError, match="unavailable"):
        resolve_odds_references(*args, as_of=NOW)


def test_correction_selects_new_venue_without_changing_original_evidence() -> None:
    args = setup_references()
    before = resolve_odds_references(*args, as_of=NOW)
    keys, mappings, _, _, venues = args
    original = mappings.history.side_effect
    row = original(keys.venues[0])[0]
    later = NOW + timedelta(days=1)
    new_venue = replace(before.venues[0], venue_id=VenueId("corrected"))
    correction = replace(
        row,
        revision=2,
        canonical_entity_id=new_venue.venue_id,
        available_at=later,
        ingested_at=later,
    )
    mappings.history.side_effect = lambda key: (
        (row, correction) if key == keys.venues[0] else original(key)
    )
    venues.get.side_effect = {
        before.venues[0].venue_id: before.venues[0],
        new_venue.venue_id: new_venue,
    }.get
    assert resolve_odds_references(*args, as_of=NOW) == before
    after = resolve_odds_references(*args, as_of=later)
    assert after.venues == (new_venue,)
    assert after.revisions[-1] == correction
    assert before.revisions[-1] == row


def test_selected_evidence_survives_later_revocation() -> None:
    args = setup_references()
    result = resolve_odds_references(*args, as_of=NOW)
    keys, mappings, *_ = args
    original = mappings.history.side_effect
    row = original(keys.event)[0]
    later = NOW + timedelta(days=1)
    mappings.history.side_effect = lambda key: (
        (
            row,
            replace(
                row, revision=2, status=MappingStatus.REVOKED, available_at=later, ingested_at=later
            ),
        )
        if key == keys.event
        else original(key)
    )
    assert resolve_odds_references(*args, as_of=NOW) == result
    with pytest.raises(ValueError):
        resolve_odds_references(*args, as_of=later)
    assert result.revisions[1] == row
