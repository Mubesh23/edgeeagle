from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from unittest.mock import Mock

import pytest

from edgeeagle_domain.raw import RawPayload
from edgeeagle_ingestion.odds_acceptance import OddsCaptureRepository
from edgeeagle_ingestion.odds_import import import_odds_capture
from edgeeagle_ingestion.odds_normalization import normalize_odds_capture
from tests.unit.test_odds_manifest import NOW
from tests.unit.test_odds_normalization import inputs


@pytest.mark.parametrize("failure", [None, "missing", "changed", "commit", "count"])
def test_odds_import_order_and_readback(failure: str | None) -> None:
    manifest, guard, _, store, _, reads = inputs()
    expected = normalize_odds_capture(store, manifest, (guard,), reads, as_of=NOW)
    raw = RawPayload(capture=manifest.raw.capture, body=store.get.return_value)
    store.reset_mock()
    store.put.return_value = raw.reference()
    importer = Mock()
    importer.read.return_value = raw
    repo = Mock(spec=OddsCaptureRepository)
    repo.accept.return_value = 2 if failure == "count" else 1
    repo.get.return_value = (
        None
        if failure == "missing"
        else replace(expected, normalizer_version="unknown")
        if failure == "changed"
        else expected
    )
    events = []

    @contextmanager
    def transactions() -> Iterator[OddsCaptureRepository]:
        store.put.assert_called_once_with(raw)
        assert store.get.call_count == 2  # Normalize, then verify replay, both before writes.
        events.append("enter")
        yield repo
        events.append("commit")
        if failure == "commit":
            raise RuntimeError("commit failed")

    if failure:
        with pytest.raises((ValueError, RuntimeError)):
            import_odds_capture(importer, store, manifest, (guard,), reads, transactions, as_of=NOW)
    else:
        result = import_odds_capture(
            importer, store, manifest, (guard,), reads, transactions, as_of=NOW
        )
        assert result.inserted_receipts == 1 and result.raw == raw.reference()
        assert events == ["enter", "commit"]
    assert store.get.call_count == 2


def test_odds_import_manifest_mismatch_stops_before_reads_or_writes() -> None:
    manifest, guard, _, store, _, _ = inputs()
    raw = RawPayload(capture=manifest.raw.capture, body=b"[]")
    importer, reads, writes = Mock(), Mock(), Mock()
    importer.read.return_value = raw
    store.put.return_value = raw.reference()
    with pytest.raises(ValueError, match="manifest"):
        import_odds_capture(importer, store, manifest, (guard,), reads, writes, as_of=NOW)
    reads.assert_not_called()
    writes.assert_not_called()
