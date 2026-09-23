from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest

from edgeeagle_domain.mappings import (
    CanonicalEntityId,
    MappingStatus,
    ProviderEntityKey,
    ProviderMappingRevision,
)
from edgeeagle_domain.provenance import DataSourceId
from edgeeagle_domain.sports import CompetitionId, ParticipantId, SportId
from edgeeagle_ingestion.fixture_references import FixtureReferenceKeys, resolve_fixture_references
from tests.unit.test_event_normalization import binding

NOW = datetime(2026, 9, 23, tzinfo=UTC)


def setup_references() -> tuple[FixtureReferenceKeys, Mock, Mock]:
    context = binding()
    keys = FixtureReferenceKeys(
        **{
            role: ProviderEntityKey(
                data_source_id=context.key.data_source_id,
                provider_entity_type="authored-fixture-reference",
                provider_entity_id=role,
            )
            for role in ("sport", "competition", "season", "home", "away")
        }
    )
    records = (context.sport, context.competition, context.season, context.home, context.away)
    ids: tuple[CanonicalEntityId, ...] = (
        context.sport.sport_id,
        context.competition.competition_id,
        context.season.season_id,
        context.home.participant_id,
        context.away.participant_id,
    )
    rows = {
        key: (
            ProviderMappingRevision(
                key=key,
                revision=1,
                canonical_entity_id=target,
                mapping_method="fixture-manifest",
                confidence=None,
                validated_by="synthetic-test",
                validated_at=NOW,
                available_at=NOW,
                ingested_at=NOW,
                status=MappingStatus.MAPPED,
            ),
        )
        for key, target in zip(keys.ordered(), ids, strict=True)
    }
    mappings, sports = Mock(), Mock()
    mappings.history.side_effect = rows.__getitem__
    sports.get_sport.return_value = records[0]
    sports.get_competition.return_value = records[1]
    sports.get_season.return_value = records[2]
    sports.get_participant.side_effect = {ids[3]: records[3], ids[4]: records[4]}.get
    return keys, mappings, sports


def test_resolves_exact_references_with_revision_evidence_without_writes() -> None:
    keys, mappings, sports = setup_references()
    result = resolve_fixture_references(keys, mappings, sports, as_of=NOW)
    assert result == resolve_fixture_references(keys, mappings, sports, as_of=NOW)
    assert result.sport == binding().sport
    assert result.competition == binding().competition
    assert result.season == binding().season
    assert (result.home, result.away) == (binding().home, binding().away)
    assert result.as_of == NOW
    assert tuple(row.key for row in result.revisions) == keys.ordered()
    assert all(row.revision == 1 for row in result.revisions)
    assert {call[0] for call in mappings.mock_calls} == {"history"}
    assert {call[0] for call in sports.mock_calls} == {
        "get_sport",
        "get_competition",
        "get_season",
        "get_participant",
    }
    with pytest.raises(FrozenInstanceError):
        result.as_of = NOW  # type: ignore[misc]


@pytest.mark.parametrize("failure", ["missing", "future", "revoked", "gap", "wrong-type"])
def test_unresolvable_or_malformed_histories_fail_closed(failure: str) -> None:
    keys, mappings, sports = setup_references()
    original = mappings.history.side_effect
    row = original(keys.home)[0]
    histories = {
        "missing": (),
        "future": (
            replace(row, available_at=NOW + timedelta(days=1), ingested_at=NOW + timedelta(days=1)),
        ),
        "revoked": (row, replace(row, revision=2, status=MappingStatus.REVOKED)),
        "gap": (
            row,
            replace(
                row,
                revision=3,
                available_at=NOW + timedelta(days=1),
                ingested_at=NOW + timedelta(days=1),
            ),
        ),
        "wrong-type": (replace(row, canonical_entity_id=SportId("s1")),),
    }
    mappings.history.side_effect = lambda key: (
        histories[failure] if key == keys.home else original(key)
    )
    with pytest.raises(ValueError):
        resolve_fixture_references(keys, mappings, sports, as_of=NOW)


def test_cutoff_selects_revision_without_falling_back_after_revocation() -> None:
    keys, mappings, sports = setup_references()
    original = mappings.history.side_effect
    row = original(keys.home)[0]
    later = NOW + timedelta(days=1)
    corrected = replace(
        row,
        revision=2,
        canonical_entity_id=ParticipantId("p3"),
        available_at=later,
        ingested_at=later,
    )
    mappings.history.side_effect = lambda key: (
        (row, corrected) if key == keys.home else original(key)
    )
    old = resolve_fixture_references(keys, mappings, sports, as_of=NOW)
    sports.get_participant.side_effect = {
        ParticipantId("p3"): replace(binding().home, participant_id=ParticipantId("p3")),
        ParticipantId("p2"): binding().away,
    }.get
    new = resolve_fixture_references(keys, mappings, sports, as_of=later)
    assert old.home.participant_id == ParticipantId("p1")
    assert old.revisions[3].revision == 1
    assert new.home.participant_id == ParticipantId("p3")
    assert new.revisions[3] == corrected


@pytest.mark.parametrize("failure", ["missing", "wrong-id", "sport", "season", "collapse"])
def test_missing_and_inconsistent_canonical_references(failure: str) -> None:
    keys, mappings, sports = setup_references()
    if failure == "missing":
        sports.get_sport.return_value = None
    elif failure == "wrong-id":
        sports.get_sport.return_value = replace(binding().sport, sport_id=SportId("other"))
    elif failure == "sport":
        sports.get_competition.return_value = replace(
            binding().competition, sport_id=SportId("other")
        )
    elif failure == "season":
        sports.get_season.return_value = replace(
            binding().season, competition_id=CompetitionId("other")
        )
    else:
        original = mappings.history.side_effect
        row = replace(original(keys.away)[0], canonical_entity_id=ParticipantId("p1"))
        mappings.history.side_effect = lambda key: (row,) if key == keys.away else original(key)
    with pytest.raises(ValueError):
        resolve_fixture_references(keys, mappings, sports, as_of=NOW)


def test_invalid_keys_cutoff_and_repository_failures() -> None:
    keys, mappings, sports = setup_references()
    with pytest.raises(ValueError, match="distinct"):
        replace(keys, away=keys.home)
    with pytest.raises(ValueError, match="source"):
        replace(keys, home=replace(keys.home, data_source_id=DataSourceId("other")))
    with pytest.raises(TypeError):
        replace(keys, home=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        resolve_fixture_references(keys, mappings, sports, as_of=datetime(2026, 1, 1))
    mappings.history.assert_not_called()
    mappings.history.side_effect = OSError("unavailable")
    with pytest.raises(OSError, match="unavailable"):
        resolve_fixture_references(keys, mappings, sports, as_of=NOW)


def test_result_rejects_incomplete_evidence_and_inconsistent_participant_sport() -> None:
    keys, mappings, sports = setup_references()
    result = resolve_fixture_references(keys, mappings, sports, as_of=NOW)
    with pytest.raises(ValueError, match="five"):
        replace(result, revisions=result.revisions[:-1])
    with pytest.raises(ValueError, match="active and available"):
        replace(result, as_of=NOW - timedelta(seconds=1))
    with pytest.raises(ValueError, match="active and available"):
        replace(
            result,
            revisions=(
                replace(result.revisions[0], status=MappingStatus.REVOKED),
                *result.revisions[1:],
            ),
        )
    with pytest.raises(ValueError, match="participant and sport"):
        replace(result, home=replace(result.home, sport_id=SportId("other")))


def test_cutoff_is_canonical_utc_and_record_read_failure_propagates() -> None:
    from datetime import timezone

    keys, mappings, sports = setup_references()
    result = resolve_fixture_references(
        keys, mappings, sports, as_of=NOW.astimezone(timezone(timedelta(hours=-5)))
    )
    assert result.as_of.tzinfo is UTC
    sports.get_sport.side_effect = OSError("reference storage unavailable")
    with pytest.raises(OSError, match="reference storage unavailable"):
        resolve_fixture_references(keys, mappings, sports, as_of=NOW)
