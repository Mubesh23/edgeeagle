import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from edgeeagle_ingestion.sportmonks_parser import PARSER_VERSION, parse_scheduled_fixture

FIXTURE = Path("tests/fixtures/providers/sportmonks/scheduled-v1/fixture.json")
NOW = datetime(2026, 9, 24, 12, tzinfo=UTC)


def parse(body: bytes) -> Any:
    return parse_scheduled_fixture(body, expected_fixture_id=910001, snapshot_at=NOW)


def test_sportmonks_fixture_identity_roles_and_utc_kickoff() -> None:
    value = parse(FIXTURE.read_bytes())
    assert value.fixture_id == 910001
    assert (value.sport_id, value.league_id, value.season_id, value.state_id) == (
        1,
        920001,
        930001,
        1,
    )
    assert value.home.participant_id == 940001 and value.home.name == "Authored Home FC"
    assert value.away.participant_id == 940002 and value.away.name == "Authored Away FC"
    assert value.starts_at == datetime(2026, 10, 1, 18, tzinfo=UTC)
    with pytest.raises(FrozenInstanceError):
        value.fixture_id = 2
    metadata = json.loads(FIXTURE.with_name("metadata.json").read_bytes())
    assert metadata["captured_at"] is None
    assert metadata["origin"] == "AUTHORED_FIXTURE"
    assert metadata["parser_version"] == PARSER_VERSION


def test_sportmonks_order_and_additive_fields_do_not_infer_roles_or_features() -> None:
    doc = json.loads(FIXTURE.read_bytes())
    doc["data"]["participants"].reverse()
    doc["data"]["name"] = "Not a pair of team names"
    doc["data"]["venue_id"] = 777
    doc["data"]["xGFixture"] = {"not_a_supported_feature": 1.2345}
    doc["subscription"] = [{"meta": {"current_timestamp": 9999999999}}]
    assert parse(json.dumps(doc).encode()) == parse(FIXTURE.read_bytes())


@pytest.mark.parametrize(
    "path,value",
    [
        (("data",), []),
        (("data",), None),
        (("timezone",), "Europe/London"),
        (("timezone",), None),
        (("data", "id"), 910002),
        (("data", "id"), True),
        (("data", "id"), "910001"),
        (("data", "id"), 910001.0),
        (("data", "sport_id"), 2),
        (("data", "sport_id"), True),
        (("data", "league_id"), 0),
        (("data", "season_id"), -1),
        (("data", "season_id"), 2**63),
        (("data", "state_id"), 5),
        (("data", "state_id"), True),
        (("data", "state", "id"), 2),
        (("data", "state", "state"), "FT"),
        (("data", "placeholder"), True),
        (("data", "placeholder"), 0),
        (("data", "starting_at"), "2026-10-01T18:00:00Z"),
        (("data", "starting_at"), "2026-02-30 18:00:00"),
        (("data", "starting_at"), "2026-10-01 19:00:00"),
        (("data", "starting_at_timestamp"), None),
        (("data", "starting_at_timestamp"), 1790877600.0),
        (("data", "starting_at_timestamp"), 2**63 - 1),
        (("data", "participants"), []),
        (("data", "participants"), {}),
        (("data", "participants", 0, "id"), 940001),
        (("data", "participants", 0, "sport_id"), 2),
        (("data", "participants", 0, "placeholder"), True),
        (("data", "participants", 0, "meta", "location"), "home"),
        (("data", "participants", 0, "meta", "location"), "neutral"),
        (("data", "participants", 0, "name"), ""),
        (("data", "participants", 0, "name"), " padded"),
        (("data", "participants", 0, "name"), "x" * 257),
        (("data", "participants", 0, "name"), "bad\u0000name"),
        (("data", "participants", 0, "name"), "\ud800"),
    ],
)
def test_sportmonks_invalid_values_fail_closed(path: tuple[str | int, ...], value: Any) -> None:
    doc = json.loads(FIXTURE.read_bytes())
    parent = doc
    for key in path[:-1]:
        parent = parent[key]
    parent[path[-1]] = value
    with pytest.raises(ValueError):
        parse(json.dumps(doc).encode())


@pytest.mark.parametrize(
    "field",
    [
        "id",
        "sport_id",
        "league_id",
        "season_id",
        "state_id",
        "state",
        "placeholder",
        "starting_at",
        "starting_at_timestamp",
        "participants",
    ],
)
def test_sportmonks_missing_required_fixture_fields(field: str) -> None:
    doc = json.loads(FIXTURE.read_bytes())
    del doc["data"][field]
    with pytest.raises(ValueError):
        parse(json.dumps(doc).encode())


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"[]",
        b"{}",
        b'{"data":null}',
        b'{"data":1,"data":2}',
        b'{"error":"authored error"}',
        b"\xff",
        b"NaN",
        b"Infinity",
        b" " * (1024 * 1024 + 1),
        b"[" * 2000 + b"]" * 2000,
    ],
)
def test_sportmonks_malformed_envelopes(body: bytes) -> None:
    with pytest.raises(ValueError):
        parse(body)


@pytest.mark.parametrize("expected", [True, 0, -1, "910001", 910001.0, 2**63])
def test_sportmonks_expected_native_id_is_explicit_integer(expected: Any) -> None:
    with pytest.raises(ValueError):
        parse_scheduled_fixture(FIXTURE.read_bytes(), expected_fixture_id=expected, snapshot_at=NOW)


def test_sportmonks_snapshot_must_be_aware_and_strictly_before_kickoff() -> None:
    with pytest.raises(ValueError):
        parse_scheduled_fixture(
            FIXTURE.read_bytes(), expected_fixture_id=910001, snapshot_at=NOW.replace(tzinfo=None)
        )
    for instant in (datetime(2026, 10, 1, 18, tzinfo=UTC), datetime(2026, 10, 2, tzinfo=UTC)):
        with pytest.raises(ValueError):
            parse_scheduled_fixture(
                FIXTURE.read_bytes(), expected_fixture_id=910001, snapshot_at=instant
            )
    assert parse_scheduled_fixture(
        FIXTURE.read_bytes(),
        expected_fixture_id=910001,
        snapshot_at=NOW.astimezone(timezone(timedelta(hours=-5))),
    ) == parse(FIXTURE.read_bytes())
