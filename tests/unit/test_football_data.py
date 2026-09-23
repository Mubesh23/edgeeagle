"""Authored CSV results, explicit context, no provider calls."""

from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from edgeeagle_domain.provenance import DataSourceId
from edgeeagle_domain.raw import RawPayload, RawPayloadIntegrityError
from edgeeagle_domain.sports import EventId
from edgeeagle_ingestion.events import EventCandidate
from edgeeagle_ingestion.fixture_references import resolve_fixture_references
from edgeeagle_ingestion.football_data import (
    FootballDataRequest,
    normalize_results,
    replay_results,
    row_locator,
)
from tests.unit.test_event_normalization import fixture_payload
from tests.unit.test_fixture_references import NOW, setup_references
from tests.unit.test_mapped_normalization import request

CSV_PATH = Path(__file__).parents[1] / "fixtures/providers/football_data/results.csv"


def csv_payload() -> RawPayload:
    base = fixture_payload()
    return replace(
        base,
        capture=replace(base.capture, resource="football-data-results-v1"),
        body=CSV_PATH.read_bytes(),
    )


def csv_requests() -> tuple[FootballDataRequest, ...]:
    base = request()
    return tuple(
        FootballDataRequest(
            key=replace(
                base.key,
                provider_entity_id=row_locator(
                    csv_payload().capture.resource,
                    "SX",
                    date(2026, 8, day),
                    base.home_label,
                    base.away_label,
                ),
            ),
            references=base.references,
            division="SX",
            home_label=base.home_label,
            away_label=base.away_label,
            event_id=EventId(f"csv-{day}"),
            context_version="authored-csv-context-v1",
            utc_offset_minutes=60,
        )
        for day in (1, 8)
    )


def resolver() -> Mock:
    keys, mappings, sports = setup_references()
    result = Mock()
    result.resolve.return_value = resolve_fixture_references(keys, mappings, sports, as_of=NOW)
    return result


def normalized() -> tuple[EventCandidate, ...]:
    raw, store, references = csv_payload(), Mock(), resolver()
    store.get.return_value = raw.body

    @contextmanager
    def reads() -> Any:
        yield references

    return normalize_results(store, raw.reference(), csv_requests(), reads, as_of=NOW)


def test_csv_complete_normalization_and_retained_replay() -> None:
    values = normalized()
    assert [v.event.event_id.value for v in values] == ["csv-1", "csv-8"]
    assert values[0].event.starts_at == datetime(2026, 8, 1, 14, tzinfo=UTC)
    assert values[0].event.status == "FINISHED"
    assert values[0].soccer_result is not None
    assert values[1].soccer_result is not None
    assert (values[0].soccer_result.home_goals, values[0].soccer_result.away_goals) == (2, 1)
    assert values[1].soccer_result.home_goals == 0
    assert values[0].raw.capture.available_at is None
    raw, store = csv_payload(), Mock()
    store.get.return_value = raw.body
    assert replay_results(store, raw.reference(), tuple(reversed(values))) == values
    store.put.assert_not_called()


@pytest.mark.parametrize(
    "before,after",
    [
        (b"FTHG", b"Missing"),
        (b"FTR", b"FTHG"),
        (b"01/08/2026", b"01/08/26"),
        (b"01/08/2026", b"31/02/2026"),
        (b"15:00", b""),
        (b"15:00", b"25:00"),
        (b",2,1,H,", b",-1,1,A,"),
        (b",2,1,H,", b",2.0,1,H,"),
        (b",2,1,H,", b",2,1,D,"),
        (b",2,1,H,", b",2,,H,"),
        (b"UnusedNote", b""),
        (b"authored example", b"extra,field"),
        (b"authored example", b'"unterminated'),
        (b"SX,01", b" SX,01"),
        (b"Synthetic Away FC", b"Synthetic Home FC"),
        (b"\nSX,08", b"\n\nSX,08"),
        (b"authored example", b"nul\x00"),
    ],
)
def test_bad_csv_fails_before_reference_reads(before: bytes, after: bytes) -> None:
    raw = replace(csv_payload(), body=csv_payload().body.replace(before, after))
    store, reads = Mock(), Mock()
    store.get.return_value = raw.body
    with pytest.raises((ValueError, UnicodeError)):
        normalize_results(store, raw.reference(), csv_requests(), reads, as_of=NOW)
    reads.assert_not_called()


@pytest.mark.parametrize(
    "failure",
    [
        "empty",
        "duplicate",
        "bytes",
        "rows",
        "encoding",
        "missing",
        "corrupt",
        "coverage",
        "identity",
    ],
)
def test_csv_limits_and_batch_coverage(failure: str) -> None:
    raw, store, reads, requests = csv_payload(), Mock(), Mock(), csv_requests()
    lines = raw.body.splitlines(keepends=True)
    if failure == "empty":
        raw = replace(raw, body=lines[0])
    elif failure == "duplicate":
        raw = replace(raw, body=raw.body + lines[1])
    elif failure == "bytes":
        raw = replace(raw, body=b"x" * (1_048_576 + 1))
    elif failure == "rows":
        raw = replace(raw, body=lines[0] + lines[1] * 101)
    elif failure == "encoding":
        raw = replace(raw, body=b"\xff")
    elif failure == "coverage":
        requests = requests[:1]
    elif failure == "identity":
        requests = (requests[0], replace(requests[1], event_id=requests[0].event_id))
    store.get.return_value = (
        None if failure == "missing" else b"corrupt" if failure == "corrupt" else raw.body
    )
    with pytest.raises((ValueError, FileNotFoundError, RawPayloadIntegrityError)):
        normalize_results(store, raw.reference(), requests, reads, as_of=NOW)
    reads.assert_not_called()


def test_replay_rejects_changed_output_and_unsupported_versions() -> None:
    raw, store = csv_payload(), Mock()
    store.get.return_value = raw.body
    values = normalized()
    with pytest.raises(ValueError, match="reproduce"):
        replay_results(
            store,
            raw.reference(),
            (replace(values[0], event=replace(values[0].event, venue_location="drift")), values[1]),
        )
    store.reset_mock()
    with pytest.raises(ValueError):
        replay_results(
            store, raw.reference(), (replace(values[0], parser_version="future"), values[1])
        )
    store.get.assert_not_called()


@pytest.mark.parametrize("failure", ["source", "type", "labels", "offset"])
def test_invalid_request(failure: str) -> None:
    value = csv_requests()[0]
    with pytest.raises(ValueError):
        if failure == "source":
            replace(value, key=replace(value.key, data_source_id=DataSourceId("other")))
        elif failure == "type":
            replace(value, key=replace(value.key, provider_entity_type="participant"))
        elif failure == "labels":
            replace(value, away_label=value.home_label)
        else:
            replace(value, utc_offset_minutes=True)


@pytest.mark.parametrize(
    "failure", ["labels", "source", "cutoff", "keys", "season", "close", "resolve"]
)
def test_context_failures_return_no_batch(failure: str) -> None:
    raw, store, references = csv_payload(), Mock(), resolver()
    requests = csv_requests()
    refs = references.resolve.return_value
    if failure == "labels":
        requests = (replace(requests[0], division="OTHER"), requests[1])
    elif failure == "source":
        raw = replace(raw, capture=replace(raw.capture, data_source_id=DataSourceId("other")))
    elif failure == "cutoff":
        references.resolve.return_value = replace(refs, as_of=NOW + timedelta(days=1))
    elif failure == "keys":
        references.resolve.return_value = replace(
            refs,
            revisions=(
                replace(
                    refs.revisions[0],
                    key=replace(refs.revisions[0].key, provider_entity_id="other"),
                ),
                *refs.revisions[1:],
            ),
        )
    elif failure == "season":
        references.resolve.return_value = replace(
            refs, season=replace(refs.season, ends_at=datetime(2026, 7, 1, tzinfo=UTC))
        )
    elif failure == "resolve":
        references.resolve.side_effect = [refs, ValueError("revoked")]
    store.get.return_value = raw.body

    @contextmanager
    def reads() -> Any:
        yield references
        if failure == "close":
            raise OSError("snapshot close failed")

    with pytest.raises((ValueError, OSError)):
        normalize_results(store, raw.reference(), requests, reads, as_of=NOW)


def test_bom_crlf_quotes_and_explicit_negative_offset() -> None:
    raw, store, references = csv_payload(), Mock(), resolver()
    raw = replace(
        raw,
        body=b"\xef\xbb\xbf"
        + raw.body.replace(b"\n", b"\r\n").replace(
            b"authored example", b'"comma, in unused column"'
        ),
    )
    store.get.return_value = raw.body

    @contextmanager
    def reads() -> Any:
        yield references

    requests = tuple(replace(r, utc_offset_minutes=-300) for r in csv_requests())
    values = normalize_results(store, raw.reference(), requests, reads, as_of=NOW)
    assert values[0].event.starts_at == datetime(2026, 8, 1, 20, tzinfo=UTC)
    assert replay_results(store, raw.reference(), values) == values


def test_row_limit_with_unique_rows_and_no_reference_reads() -> None:
    base = csv_payload()
    header = base.body.splitlines()[0] + b"\n"
    rows = b"".join(
        (
            f"SX,{(date(2026, 1, 1) + timedelta(days=i)):%d/%m/%Y},15:00,Home,Away,1,0,H,note\n"
        ).encode()
        for i in range(101)
    )
    raw, store, reads = replace(base, body=header + rows), Mock(), Mock()
    store.get.return_value = raw.body
    with pytest.raises(ValueError, match="row count"):
        normalize_results(store, raw.reference(), (), reads, as_of=NOW)
    reads.assert_not_called()
