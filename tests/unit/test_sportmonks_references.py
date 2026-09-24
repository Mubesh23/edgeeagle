from dataclasses import replace
from datetime import UTC, timedelta, timezone
from unittest.mock import Mock

import pytest

from edgeeagle_domain.mappings import MappingStatus, ProviderEntityKey
from edgeeagle_domain.provenance import DataSource, DataSourceId, SourceType
from edgeeagle_domain.sports import Event, EventId, EventParticipant, ParticipantId, SportId
from edgeeagle_ingestion.fixture_references import FixtureReferenceKeys
from edgeeagle_ingestion.sportmonks_references import (
    SportmonksReferenceKeys,
    resolve_sportmonks_references,
)
from tests.unit.test_fixture_references import setup_references as fixture_setup
from tests.unit.test_sportmonks_manifest import NOW, manifest


def setup_references() -> tuple[SportmonksReferenceKeys, Mock, Mock, Mock]:
    old_keys, mappings, sports = fixture_setup()
    source_id = manifest().raw.capture.data_source_id

    def key(kind: str, value: int) -> ProviderEntityKey:
        return ProviderEntityKey(
            data_source_id=source_id, provider_entity_type=kind, provider_entity_id=str(value)
        )

    keys = SportmonksReferenceKeys(
        context=FixtureReferenceKeys(
            sport=key("sport", 1),
            competition=key("league", 920001),
            season=key("season", 930001),
            home=key("participant", 940001),
            away=key("participant", 940002),
        ),
        event=key("fixture", 910001),
    )
    rows = {
        new: (replace(mappings.history.side_effect(old)[0], key=new),)
        for old, new in zip(old_keys.ordered(), keys.context.ordered(), strict=True)
    }
    event = Event(
        event_id=EventId("existing-event"),
        sport_id=sports.get_sport.return_value.sport_id,
        competition_id=sports.get_competition.return_value.competition_id,
        season_id=sports.get_season.return_value.season_id,
        starts_at=NOW.replace(month=10, day=1, hour=18),
        status="SCHEDULED",
    )
    season = sports.get_season.return_value
    sports.get_season.return_value = replace(
        season, starts_at=NOW - timedelta(days=30), ends_at=NOW + timedelta(days=300)
    )
    rows[keys.event] = (
        replace(rows[keys.context.sport][0], key=keys.event, canonical_entity_id=event.event_id),
    )
    mappings.history.side_effect = rows.__getitem__
    sports.get_event.return_value = event
    entries = []
    for k, role in ((keys.context.home, "HOME"), (keys.context.away, "AWAY")):
        participant_id = rows[k][0].canonical_entity_id
        assert isinstance(participant_id, ParticipantId)
        entries.append(
            EventParticipant(event_id=event.event_id, participant_id=participant_id, role=role)
        )
    sports.get_event_participants.return_value = tuple(entries)
    sources = Mock()
    sources.get.return_value = DataSource(
        data_source_id=source_id,
        code="SPORTMONKS",
        source_type=SourceType.SPORTS_DATA,
        capabilities=frozenset(),
    )
    return keys, mappings, sports, sources


def test_resolves_six_explicit_mappings_without_writes() -> None:
    args = setup_references()
    result = resolve_sportmonks_references(*args, as_of=NOW)
    assert tuple(r.key for r in result.revisions) == args[0].ordered()
    assert result.as_of == NOW and result.as_of.tzinfo is UTC
    assert result.source.code == "SPORTMONKS"
    assert result.event.event_id == EventId("existing-event")
    assert len(result.entries) == 2
    assert resolve_sportmonks_references(*args, as_of=NOW) == result
    for repo in args[1:]:
        assert all(c[0] == "history" or c[0].startswith("get") for c in repo.mock_calls)


@pytest.mark.parametrize("index", range(6))
@pytest.mark.parametrize("failure", ["missing", "future", "revoked", "gap", "wrong-type"])
def test_all_mapping_roles_fail_closed(index: int, failure: str) -> None:
    args = setup_references()
    keys, mappings, *_ = args
    key = keys.ordered()[index]
    original = mappings.history.side_effect
    row = original(key)[0]
    future = NOW + timedelta(days=1)
    histories = {
        "missing": (),
        "future": (replace(row, available_at=future, ingested_at=future),),
        "revoked": (row, replace(row, revision=2, status=MappingStatus.REVOKED)),
        "gap": (row, replace(row, revision=3, available_at=future, ingested_at=future)),
        "wrong-type": (
            replace(row, canonical_entity_id=EventId("wrong") if index != 5 else SportId("wrong")),
        ),
    }
    mappings.history.side_effect = lambda k: histories[failure] if k == key else original(k)
    with pytest.raises(ValueError):
        resolve_sportmonks_references(*args, as_of=NOW)


@pytest.mark.parametrize(
    "record", ["source", "sport", "competition", "season", "participant", "event"]
)
def test_missing_records(record: str) -> None:
    args = setup_references()
    method = args[3].get if record == "source" else getattr(args[2], f"get_{record}")
    method.side_effect = None
    method.return_value = None
    with pytest.raises(ValueError):
        resolve_sportmonks_references(*args, as_of=NOW)


def test_result_rejects_inconsistent_evidence_and_roles() -> None:
    result = resolve_sportmonks_references(*setup_references(), as_of=NOW)
    for changes in (
        {"source": replace(result.source, code="OTHER")},
        {"source": replace(result.source, source_type=SourceType.VENUE_API)},
        {"source": replace(result.source, data_source_id=DataSourceId("other"))},
        {"context": replace(result.context, sport=replace(result.context.sport, code="other"))},
        {
            "context": replace(
                result.context, home=replace(result.context.home, participant_type="PERSON")
            )
        },
        {"event": replace(result.event, event_id=EventId("wrong"))},
        {"event": replace(result.event, season_id=type(result.event.season_id)("wrong"))},
        {"entries": ()},
        {"entries": (result.entries[0], replace(result.entries[1], role="HOME"))},
        {"event_revision": replace(result.event_revision, status=MappingStatus.REVOKED)},
        {"event_revision": replace(result.event_revision, canonical_entity_id=EventId("wrong"))},
        {
            "event_revision": replace(
                result.event_revision,
                available_at=NOW + timedelta(days=1),
                ingested_at=NOW + timedelta(days=1),
            )
        },
    ):
        with pytest.raises(ValueError):
            replace(result, **changes)


def test_keys_reject_wrong_namespaces_ids_and_sources() -> None:
    keys, *_ = setup_references()
    with pytest.raises(ValueError):
        replace(
            keys,
            context=replace(
                keys.context, sport=replace(keys.context.sport, provider_entity_id="2")
            ),
        )
    for key in (
        replace(keys.event, data_source_id=DataSourceId("other")),
        replace(keys.event, provider_entity_type="event"),
        *(
            replace(keys.event, provider_entity_id=value)
            for value in ("0", "01", "1.0", "-1", str(2**63), "1" * 100)
        ),
    ):
        with pytest.raises(ValueError):
            replace(keys, event=key)


def test_cutoff_and_read_errors() -> None:
    args = setup_references()
    with pytest.raises(ValueError):
        resolve_sportmonks_references(*args, as_of=NOW.replace(tzinfo=None))
    args[1].history.assert_not_called()
    result = resolve_sportmonks_references(
        *args, as_of=NOW.astimezone(timezone(timedelta(hours=2)))
    )
    assert result.as_of.tzinfo is UTC
    args[1].history.side_effect = OSError("unavailable")
    with pytest.raises(OSError):
        resolve_sportmonks_references(*args, as_of=NOW)
