"""Whole-capture bounds and replay; wholly authored rows, no downloaded data."""

from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import Mock

import pytest

from edgeeagle_domain.raw import RawPayload
from edgeeagle_domain.sports import EventId
from edgeeagle_ingestion.football_data import (
    SEASON_PARSER_VERSION,
    FootballDataRequest,
    normalize_results,
    normalize_season_results,
    replay_results,
    replay_season_results,
    row_locator,
)
from tests.unit.test_fixture_references import NOW
from tests.unit.test_football_data import csv_payload, csv_requests, normalized, resolver


def season_batch(count: int) -> tuple[RawPayload, tuple[FootballDataRequest, ...]]:
    raw, request = csv_payload(), csv_requests()[0]
    rows, requests = [], []
    for index in range(count):
        day = date(2026, 1, 1) + timedelta(days=index)
        rows.append(f"SX,{day:%d/%m/%Y},15:00,{request.home_label},{request.away_label},2,1,H\n")
        requests.append(
            replace(
                request,
                key=replace(
                    request.key,
                    provider_entity_id=row_locator(
                        raw.capture.resource, "SX", day, request.home_label, request.away_label
                    ),
                ),
                event_id=EventId(f"season-{index:03}"),
            )
        )
    body = ("Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR\n" + "".join(rows)).encode()
    return replace(raw, body=body), tuple(requests)


def season_resolver() -> Mock:
    result = resolver()
    refs = result.resolve.return_value
    result.resolve.return_value = replace(
        refs, season=replace(refs.season, ends_at=datetime(2028, 1, 1, tzinfo=UTC))
    )
    return result


@pytest.mark.parametrize("count", [1, 100, 380, 512])
def test_complete_season_profile_and_retained_replay(count: int) -> None:
    raw, requests = season_batch(count)
    store, references = Mock(), season_resolver()
    store.get.return_value = raw.body
    openings = []

    @contextmanager
    def reads() -> Any:
        openings.append(True)
        yield references

    values = normalize_season_results(store, raw.reference(), requests, reads, as_of=NOW)
    assert len(values) == count
    assert openings == [True]
    assert references.resolve.call_count == count
    assert all(v.parser_version == SEASON_PARSER_VERSION for v in values)
    assert all(v.raw == raw.reference() and v.raw.capture.available_at is None for v in values)
    assert replay_season_results(store, raw.reference(), tuple(reversed(values))) == values
    with pytest.raises(ValueError, match="supported"):
        replay_results(store, raw.reference(), values)
    store.put.assert_not_called()


@pytest.mark.parametrize("failure", ["513", "last-row", "duplicate", "coverage", "bytes"])
def test_season_rejects_invalid_complete_capture_before_references(failure: str) -> None:
    raw, requests = season_batch(513 if failure == "513" else 380)
    if failure == "last-row":
        raw = replace(raw, body=raw.body[:-6] + b"bad\n")
    elif failure == "duplicate":
        raw = replace(raw, body=raw.body + raw.body.splitlines(keepends=True)[1])
    elif failure == "coverage":
        requests = requests[:-1]
    elif failure == "bytes":
        raw = replace(raw, body=b"x" * (1_048_576 + 1))
    store, reads = Mock(), Mock()
    store.get.return_value = raw.body
    with pytest.raises(ValueError):
        normalize_season_results(store, raw.reference(), requests, reads, as_of=NOW)
    reads.assert_not_called()


def test_season_and_legacy_pins_do_not_mix_or_change_legacy_bounds() -> None:
    store, reads = Mock(), Mock()
    raw, requests = season_batch(101)
    store.get.return_value = raw.body
    with pytest.raises(ValueError, match="row count"):
        normalize_results(store, raw.reference(), requests, reads, as_of=NOW)
    reads.assert_not_called()
    legacy = normalized()
    with pytest.raises(ValueError, match="supported"):
        replay_season_results(store, legacy[0].raw, legacy)


def test_season_replay_checks_raw_integrity_and_final_output() -> None:
    raw, requests = season_batch(380)
    store = Mock()
    store.get.return_value = raw.body

    @contextmanager
    def reads() -> Any:
        yield season_resolver()

    values = normalize_season_results(store, raw.reference(), requests, reads, as_of=NOW)
    assert values[-1].soccer_result is not None
    changed = replace(values[-1], soccer_result=replace(values[-1].soccer_result, home_goals=3))
    with pytest.raises(ValueError, match="reproduce"):
        replay_season_results(store, raw.reference(), (*values[:-1], changed))
    store.get.return_value = None
    with pytest.raises(FileNotFoundError):
        replay_season_results(store, raw.reference(), values)
