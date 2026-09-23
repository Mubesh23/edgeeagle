import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from edgeeagle_domain.mappings import ProviderEntityKey
from edgeeagle_domain.provenance import DataSourceId
from edgeeagle_domain.raw import RawCapture, RawPayload, RawPayloadIntegrityError
from edgeeagle_domain.sports import (
    Competition,
    CompetitionId,
    EventId,
    Participant,
    ParticipantId,
    Season,
    SeasonId,
    Sport,
    SportId,
)
from edgeeagle_ingestion.synthetic_events import FixtureEventBinding, normalize_fixture_events


def fixture_payload() -> RawPayload:
    path = Path(__file__).parents[1] / "fixtures/providers/the_odds_api/odds-success.json"
    return RawPayload(
        capture=RawCapture(
            data_source_id=DataSourceId("synthetic-fixtures"),
            resource="the-odds-api-soccer-h2h-v1",
            ingested_at=datetime(2026, 9, 22, tzinfo=UTC),
        ),
        body=path.read_bytes(),
    )


def binding() -> FixtureEventBinding:
    sport = Sport(sport_id=SportId("s1"), code="soccer", name="Soccer")
    competition = Competition(
        competition_id=CompetitionId("c1"),
        sport_id=sport.sport_id,
        name="Synthetic league",
        country_or_region="test",
    )
    season = Season(
        season_id=SeasonId("season1"),
        competition_id=competition.competition_id,
        name="Test season",
        starts_at=datetime(2026, 1, 1, tzinfo=UTC),
        ends_at=datetime(2026, 12, 31, tzinfo=UTC),
    )
    return FixtureEventBinding(
        key=ProviderEntityKey(
            data_source_id=DataSourceId("synthetic-fixtures"),
            provider_entity_type="event",
            provider_entity_id="synthetic-soccer-event-001",
        ),
        competition_key="soccer_epl",
        home_label="Synthetic Home FC",
        away_label="Synthetic Away FC",
        event_id=EventId("e1"),
        sport=sport,
        competition=competition,
        season=season,
        home=Participant(
            participant_id=ParticipantId("p1"),
            sport_id=sport.sport_id,
            participant_type="TEAM",
            canonical_name="Internal home",
        ),
        away=Participant(
            participant_id=ParticipantId("p2"),
            sport_id=sport.sport_id,
            participant_type="TEAM",
            canonical_name="Internal away",
        ),
        status="SCHEDULED",
        context_version="synthetic-context-v1",
    )


def test_deterministic_candidate_preserves_lineage() -> None:
    raw, context, store = fixture_payload(), binding(), Mock()
    store.get.return_value = raw.body
    result = normalize_fixture_events(store, raw.reference(), (context,))
    assert result == normalize_fixture_events(store, raw.reference(), (context,))
    candidate = result[0]
    assert candidate.event.event_id == EventId("e1")
    assert candidate.event.starts_at == datetime(2026, 10, 1, 18, tzinfo=UTC)
    assert [entry.role for entry in candidate.entries] == ["HOME", "AWAY"]
    assert candidate.raw == raw.reference()
    assert candidate.provider_key == context.key
    assert candidate.context_version == context.context_version
    assert candidate.parser_version == "synthetic-odds-events-v1"
    assert candidate.normalizer_version == "synthetic-event-bindings-v1"
    assert candidate.raw.capture.available_at is None
    store.put.assert_not_called()


@pytest.mark.parametrize(
    "body", [b"{", b"{}", b"[null]", b"\xff", b"[NaN]", b'[{"id":"a","id":"b"}]', b"[{}]"]
)
def test_invalid_payload_fails_whole_batch(body: bytes) -> None:
    raw, store = replace(fixture_payload(), body=body), Mock()
    store.get.return_value = body
    with pytest.raises(ValueError):
        normalize_fixture_events(store, raw.reference(), (binding(),))


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", 1),
        ("id", " "),
        ("commence_time", "2026-01-01"),
        ("commence_time", "invalid"),
        ("home_team", "Synthetic Away FC"),
    ],
)
def test_bad_event_fields(field: str, value: object) -> None:
    rows = json.loads(fixture_payload().body)
    rows[0][field] = value
    raw, store = replace(fixture_payload(), body=json.dumps(rows).encode()), Mock()
    store.get.return_value = raw.body
    with pytest.raises(ValueError):
        normalize_fixture_events(store, raw.reference(), (binding(),))


def test_missing_or_corrupt_raw_is_not_parsed() -> None:
    store = Mock()
    store.get.return_value = None
    with pytest.raises(FileNotFoundError):
        normalize_fixture_events(store, fixture_payload().reference(), (binding(),))
    store.get.return_value = b"[]"
    with pytest.raises(RawPayloadIntegrityError):
        normalize_fixture_events(store, fixture_payload().reference(), (binding(),))


@pytest.mark.parametrize(
    "field,value", [("home_label", "wrong"), ("away_label", "wrong"), ("competition_key", "wrong")]
)
def test_explicit_labels_must_match(field: str, value: str) -> None:
    store = Mock()
    store.get.return_value = fixture_payload().body
    with pytest.raises(ValueError):
        normalize_fixture_events(
            store,
            fixture_payload().reference(),
            (replace(binding(), **{field: value}),),  # type: ignore[arg-type]
        )


def test_invalid_binding_and_argument_types() -> None:
    with pytest.raises(TypeError):
        replace(binding(), home=None)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        replace(binding(), context_version=" ")
    with pytest.raises(ValueError):
        replace(binding(), key=replace(binding().key, provider_entity_type="participant"))
    with pytest.raises(TypeError):
        normalize_fixture_events(Mock(), None, ())  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        normalize_fixture_events(Mock(), fixture_payload().reference(), [])  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        normalize_fixture_events(Mock(), fixture_payload().reference(), (None,))  # type: ignore[arg-type]


def test_resolution_requires_complete_unambiguous_consistent_context() -> None:
    store = Mock()
    raw, context = fixture_payload(), binding()
    store.get.return_value = raw.body
    wrong_source = replace(context, key=replace(context.key, data_source_id=DataSourceId("other")))
    wrong_season = replace(
        context, season=replace(context.season, competition_id=CompetitionId("c2"))
    )
    wrong_sport = replace(context, home=replace(context.home, sport_id=SportId("other")))
    for contexts in (
        (),
        (context, context),
        (wrong_source,),
        (wrong_season,),
        (wrong_sport,),
        (replace(context, away=context.home),),
    ):
        with pytest.raises(ValueError):
            normalize_fixture_events(store, raw.reference(), contexts)
    store.put.assert_not_called()


def test_duplicate_event_ids_and_canonical_identity_collapse() -> None:
    rows = json.loads(fixture_payload().body)
    rows.append(rows[0].copy())
    raw, store = replace(fixture_payload(), body=json.dumps(rows).encode()), Mock()
    store.get.return_value = raw.body
    with pytest.raises(ValueError, match="duplicate event"):
        normalize_fixture_events(store, raw.reference(), (binding(),))
    rows[1]["id"] = "second-event"
    raw = replace(raw, body=json.dumps(rows).encode())
    store.get.return_value = raw.body
    second = replace(binding(), key=replace(binding().key, provider_entity_id="second-event"))
    with pytest.raises(ValueError, match="identity collapse"):
        normalize_fixture_events(store, raw.reference(), (binding(), second))
    result = normalize_fixture_events(
        store, raw.reference(), (binding(), replace(second, event_id=EventId("e2")))
    )
    assert len(result) == 2


def test_empty_batch_and_unknown_fields_and_timezone_offsets() -> None:
    store = Mock()
    raw = replace(fixture_payload(), body=b"[]")
    store.get.return_value = raw.body
    assert normalize_fixture_events(store, raw.reference(), ()) == ()
    rows = json.loads(fixture_payload().body)
    rows[0]["new_field"] = {"ignored": True}
    rows[0]["commence_time"] = "2026-10-01T13:00:00-05:00"
    raw = replace(raw, body=json.dumps(rows).encode())
    store.get.return_value = raw.body
    candidate = normalize_fixture_events(store, raw.reference(), (binding(),))[0]
    assert candidate.event.starts_at == datetime(2026, 10, 1, 18, tzinfo=UTC)


def test_same_length_corruption_and_storage_failure_propagate() -> None:
    raw, store = fixture_payload(), Mock()
    store.get.return_value = b"x" * len(raw.body)
    with pytest.raises(RawPayloadIntegrityError):
        normalize_fixture_events(store, raw.reference(), (binding(),))
    store.get.side_effect = OSError("storage unavailable")
    with pytest.raises(OSError):
        normalize_fixture_events(store, raw.reference(), (binding(),))
