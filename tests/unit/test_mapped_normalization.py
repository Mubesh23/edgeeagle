import json
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from typing import Any
from unittest.mock import Mock

import pytest

from edgeeagle_domain.provenance import DataSourceId
from edgeeagle_domain.raw import RawPayloadIntegrityError, RawPayloadReference
from edgeeagle_domain.sports import EventId
from edgeeagle_ingestion.fixture_references import resolve_fixture_references
from edgeeagle_ingestion.synthetic_events import (
    MappedFixtureRequest,
    normalize_mapped_fixture_events,
)
from tests.unit.test_event_normalization import binding, fixture_payload
from tests.unit.test_fixture_references import NOW, setup_references


def request() -> MappedFixtureRequest:
    context = binding()
    keys, _, _ = setup_references()
    return MappedFixtureRequest(
        key=context.key,
        references=keys,
        competition_key=context.competition_key,
        home_label=context.home_label,
        away_label=context.away_label,
        event_id=context.event_id,
        status=context.status,
        context_version=context.context_version,
    )


def test_mapped_normalization_preserves_evidence_and_closes_snapshot() -> None:
    raw, store = fixture_payload(), Mock()
    keys, mappings, sports = setup_references()
    refs = resolve_fixture_references(keys, mappings, sports, as_of=NOW)
    resolver = Mock()
    resolver.resolve.return_value = refs
    order = []

    def get(reference: RawPayloadReference) -> bytes:
        order.append("raw")
        return raw.body

    store.get.side_effect = get

    @contextmanager
    def reads() -> Any:
        order.append("open")
        yield resolver
        order.append("close")

    result = normalize_mapped_fixture_events(store, raw.reference(), (request(),), reads, as_of=NOW)
    assert order == ["raw", "open", "close"]
    resolver.resolve.assert_called_once_with(keys, as_of=NOW)
    assert result[0].mapping_evidence is not None
    assert result[0].mapping_evidence.references == refs
    assert result[0].raw == raw.reference()
    assert result[0].raw.capture.available_at is None
    assert result[0].normalizer_version == "synthetic-event-mappings-v1"
    assert result[0].parser_version == "synthetic-odds-events-v1"
    assert result == normalize_mapped_fixture_events(
        store, raw.reference(), (request(),), reads, as_of=NOW
    )
    store.put.assert_not_called()


@pytest.mark.parametrize(
    "failure", ["missing", "corrupt", "labels", "duplicate", "coverage", "source", "naive"]
)
def test_invalid_batch_fails_before_snapshot(failure: str) -> None:
    raw, store, reads = fixture_payload(), Mock(), Mock()
    store.get.return_value = raw.body
    requests: tuple[MappedFixtureRequest, ...] = (request(),)
    cutoff = NOW
    if failure == "missing":
        store.get.return_value = None
    elif failure == "corrupt":
        store.get.return_value = b"[]"
    elif failure == "labels":
        requests = (replace(request(), home_label="wrong"),)
    elif failure == "duplicate":
        requests = (request(), request())
    elif failure == "coverage":
        requests = ()
    elif failure == "source":
        raw = replace(raw, capture=replace(raw.capture, data_source_id=DataSourceId("other")))
    else:
        cutoff = datetime(2026, 1, 1)
    with pytest.raises((ValueError, FileNotFoundError, RawPayloadIntegrityError)):
        normalize_mapped_fixture_events(store, raw.reference(), requests, reads, as_of=cutoff)
    reads.assert_not_called()


def test_mapping_or_snapshot_exit_failure_never_returns_partial_results() -> None:
    raw, store = fixture_payload(), Mock()
    store.get.return_value = raw.body
    keys, mappings, sports = setup_references()
    resolver = Mock()
    resolver.resolve.return_value = resolve_fixture_references(keys, mappings, sports, as_of=NOW)

    @contextmanager
    def reads() -> Any:
        yield resolver
        raise OSError("snapshot failed")

    with pytest.raises(OSError, match="snapshot failed"):
        normalize_mapped_fixture_events(store, raw.reference(), (request(),), reads, as_of=NOW)
    resolver.resolve.side_effect = ValueError("revoked")
    with pytest.raises(ValueError, match="revoked"):
        normalize_mapped_fixture_events(store, raw.reference(), (request(),), reads, as_of=NOW)


def test_manifest_rejects_wrong_sources_and_event_keys() -> None:
    with pytest.raises(ValueError):
        replace(request(), key=replace(request().key, data_source_id=DataSourceId("other")))
    with pytest.raises(ValueError):
        replace(request(), key=replace(request().key, provider_entity_type="participant"))
    with pytest.raises(ValueError):
        replace(request(), away_label=request().home_label)
    with pytest.raises(ValueError):
        replace(request(), status=" ")
    with pytest.raises(TypeError):
        replace(request(), references=None)  # type: ignore[arg-type]


def test_empty_batch_and_multiple_events_share_one_snapshot() -> None:
    raw, store, resolver = fixture_payload(), Mock(), Mock()
    keys, mappings, sports = setup_references()
    resolver.resolve.return_value = resolve_fixture_references(keys, mappings, sports, as_of=NOW)
    entries = []

    @contextmanager
    def reads() -> Any:
        entries.append("open")
        yield resolver

    empty = replace(raw, body=b"[]")
    store.get.return_value = empty.body
    assert normalize_mapped_fixture_events(store, empty.reference(), (), reads, as_of=NOW) == ()
    assert entries == []
    rows = json.loads(raw.body)
    rows.append(dict(rows[0], id="second-event"))
    raw = replace(raw, body=json.dumps(rows).encode())
    store.get.return_value = raw.body
    second = replace(
        request(),
        key=replace(request().key, provider_entity_id="second-event"),
        event_id=EventId("e2"),
    )
    result = normalize_mapped_fixture_events(
        store, raw.reference(), (second, request()), reads, as_of=NOW
    )
    assert [c.event.event_id.value for c in result] == ["e1", "e2"]
    assert entries == ["open"]
    assert resolver.resolve.call_count == 2
    with pytest.raises(ValueError, match="identity collapse"):
        normalize_mapped_fixture_events(
            store,
            raw.reference(),
            (request(), replace(second, event_id=request().event_id)),
            reads,
            as_of=NOW,
        )


def test_resolver_must_return_requested_keys_and_cutoff() -> None:
    raw, store, resolver = fixture_payload(), Mock(), Mock()
    store.get.return_value = raw.body
    keys, mappings, sports = setup_references()
    refs = resolve_fixture_references(keys, mappings, sports, as_of=NOW)

    @contextmanager
    def reads() -> Any:
        yield resolver

    resolver.resolve.return_value = replace(refs, as_of=NOW.replace(year=2027))
    with pytest.raises(ValueError, match="different keys or cutoff"):
        normalize_mapped_fixture_events(store, raw.reference(), (request(),), reads, as_of=NOW)
    resolver.resolve.return_value = replace(
        refs,
        revisions=(
            replace(refs.revisions[0], key=replace(keys.sport, provider_entity_id="unexpected")),
            *refs.revisions[1:],
        ),
    )
    with pytest.raises(ValueError, match="different keys or cutoff"):
        normalize_mapped_fixture_events(store, raw.reference(), (request(),), reads, as_of=NOW)
