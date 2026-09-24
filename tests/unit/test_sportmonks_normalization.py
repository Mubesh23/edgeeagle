from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from typing import Any
from unittest.mock import Mock

import pytest

from edgeeagle_domain.raw import RawPayloadIntegrityError
from edgeeagle_ingestion.sportmonks_normalization import normalize_sportmonks_capture
from edgeeagle_ingestion.sportmonks_references import resolve_sportmonks_references
from tests.unit.test_sportmonks_manifest import FIXTURE, NOW, manifest
from tests.unit.test_sportmonks_references import setup_references


def inputs() -> tuple[Any, Mock, Mock, Mock]:
    m = manifest()
    refs = resolve_sportmonks_references(*setup_references(), as_of=NOW)
    store, resolver, reads = Mock(), Mock(), Mock()
    store.get.return_value = FIXTURE.read_bytes()
    resolver.resolve.return_value = refs
    reads.return_value.__enter__ = Mock(return_value=resolver)
    reads.return_value.__exit__ = Mock(return_value=False)
    return m, store, resolver, reads


def test_retained_raw_is_read_before_one_snapshot_and_candidate_keeps_evidence() -> None:
    m, store, resolver, _ = inputs()
    active = False

    @contextmanager
    def reads() -> Any:
        nonlocal active
        store.get.assert_called_once_with(m.raw)
        active = True
        yield resolver
        active = False

    result = normalize_sportmonks_capture(store, m, reads, as_of=NOW)
    assert not active
    assert result.manifest == m
    assert result.native.fixture_id == 910001
    assert result.references == resolver.resolve.return_value
    assert result.parser_version == "sportmonks-scheduled-fixture-json-v1"
    assert result.normalizer_version == "sportmonks-scheduled-fixture-mappings-v1"
    assert result.manifest.raw.capture.available_at is None
    assert result.manifest.usage == "SYNTHETIC_ONLY"
    assert result.references.context.home.canonical_name != result.native.home.name
    resolver.resolve.assert_called_once_with(setup_references()[0], as_of=NOW)
    store.put.assert_not_called()


def test_corrupt_capture_fails_before_reference_reads() -> None:
    m, store, _, reads = inputs()
    store.get.return_value = b"corrupt"
    with pytest.raises(RawPayloadIntegrityError):
        normalize_sportmonks_capture(store, m, reads, as_of=NOW)
    reads.assert_not_called()


def test_naive_cutoff_fails_before_any_io() -> None:
    m, store, _, reads = inputs()
    with pytest.raises(ValueError):
        normalize_sportmonks_capture(store, m, reads, as_of=NOW.replace(tzinfo=None))
    store.get.assert_not_called()
    reads.assert_not_called()


@pytest.mark.parametrize("failure", ["cutoff", "key", "kickoff", "status", "season"])
def test_inconsistent_resolution_fails_closed(failure: str) -> None:
    m, store, resolver, reads = inputs()
    refs = resolver.resolve.return_value
    if failure == "cutoff":
        refs = replace(refs, context=replace(refs.context, as_of=NOW + timedelta(seconds=1)))
    elif failure == "key":
        refs = replace(
            refs,
            event_revision=replace(
                refs.event_revision,
                key=replace(refs.event_revision.key, provider_entity_id="910002"),
            ),
        )
    elif failure == "kickoff":
        refs = replace(
            refs, event=replace(refs.event, starts_at=refs.event.starts_at + timedelta(seconds=1))
        )
    elif failure == "status":
        refs = replace(refs, event=replace(refs.event, status="FINISHED"))
    else:
        refs = replace(
            refs, context=replace(refs.context, season=replace(refs.context.season, ends_at=NOW))
        )
    resolver.resolve.return_value = refs
    with pytest.raises(ValueError):
        normalize_sportmonks_capture(store, m, reads, as_of=NOW)
    reads.return_value.__exit__.assert_called_once()
    store.put.assert_not_called()


def test_resolver_failure_is_not_retried() -> None:
    m, store, resolver, reads = inputs()
    resolver.resolve.side_effect = OSError("unavailable")
    with pytest.raises(OSError):
        normalize_sportmonks_capture(store, m, reads, as_of=NOW)
    resolver.resolve.assert_called_once()
    reads.return_value.__exit__.assert_called_once()
