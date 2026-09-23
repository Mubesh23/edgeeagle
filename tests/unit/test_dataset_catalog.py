"""Catalog metadata must never imply replay success or historical eligibility."""

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest

from edgeeagle_ingestion.dataset_catalog import CatalogEntry, DatasetCatalog
from edgeeagle_ingestion.season_bundle import build_bundle, content_hash, decode_root, encode_root
from tests.unit.test_dataset_manifest import CODEC
from tests.unit.test_season_bundle import values


def catalog() -> tuple[DatasetCatalog, Mock, Mock, str]:
    raw, candidates = values(65)
    root, pages = build_bundle(raw.reference(), candidates, CODEC)
    digest = content_hash(root)
    objects, raws = Mock(), Mock()
    objects.get.side_effect = {content_hash(b): b for b in (root, *pages)}.get
    raws.get.return_value = raw.body
    return (
        DatasetCatalog((CatalogEntry(root_hash=digest, label="Authored season"),)),
        objects,
        raws,
        digest,
    )


def test_listing_reads_only_roots_and_inspection_freshly_verifies() -> None:
    selected, objects, raws, digest = catalog()
    listed = selected.list(objects)
    assert len(listed) == 1 and listed[0].replay_status == "NOT_CHECKED"
    metadata = listed[0].metadata
    assert metadata.declared_row_count == 65 and metadata.page_count == 2
    assert metadata.raw.capture.available_at is None
    assert metadata.usage == "REPLAY_ONLY" and metadata.backtest_eligible is False
    assert "RAW_AVAILABILITY_UNKNOWN" in metadata.ineligibility_reasons
    objects.get.assert_called_once_with(digest)
    instant = datetime(2026, 9, 23, tzinfo=UTC)
    report = selected.inspect(digest, CODEC, objects, raws, clock=lambda: instant)
    assert report.replay_status == "VERIFIED" and report.replay_completed_at == instant
    assert report.receipt_count == 65 and report.participant_count == 2
    assert report.metadata == metadata
    assert report.asserted_starts_at_min < report.asserted_starts_at_max
    assert report.database_acceptance_verified is False
    assert report.kickoff_accuracy_verified is False
    assert report.rights_verified is False
    assert selected.list(objects)[0].replay_status == "NOT_CHECKED"
    objects.put.assert_not_called()
    raws.put.assert_not_called()


@pytest.mark.parametrize("failure", ["root", "page", "raw", "wrong-root"])
def test_missing_or_corrupt_data_never_returns_success(failure: str) -> None:
    selected, objects, raws, digest = catalog()
    original = objects.get.side_effect
    if failure == "raw":
        raws.get.return_value = None
    else:
        objects.get.side_effect = lambda key: (
            (b"{}" if failure == "wrong-root" else None)
            if (key == digest) == (failure != "page")
            else original(key)
        )
    with pytest.raises((ValueError, FileNotFoundError)):
        selected.inspect(digest, CODEC, objects, raws, clock=lambda: datetime.now(UTC))
    objects.put.assert_not_called()
    raws.put.assert_not_called()


def test_unlisted_root_and_invalid_catalog_fail_before_io() -> None:
    selected, objects, raws, _ = catalog()
    with pytest.raises(KeyError):
        selected.inspect("a" * 64, CODEC, objects, raws, clock=lambda: datetime.now(UTC))
    objects.get.assert_not_called()
    raws.get.assert_not_called()
    assert DatasetCatalog(()).list(objects) == ()
    with pytest.raises(ValueError):
        DatasetCatalog(selected.entries * 2)
    with pytest.raises(ValueError):
        DatasetCatalog(selected.entries * 33)
    for label in ("", " trailing ", "x\nline", "x" * 121):
        with pytest.raises(ValueError):
            CatalogEntry(root_hash="a" * 64, label=label)


def test_wrong_valid_root_ordering_and_known_availability() -> None:
    raw, candidates = values(1)
    raw = replace(raw, capture=replace(raw.capture, available_at=raw.capture.ingested_at))
    candidates = tuple(replace(c, raw=raw.reference()) for c in candidates)
    root, pages = build_bundle(raw.reference(), candidates, CODEC)
    digest = content_hash(root)
    objects, raws = Mock(), Mock()
    objects.get.side_effect = {content_hash(b): b for b in (root, *pages)}.get
    raws.get.return_value = raw.body
    selected = DatasetCatalog((CatalogEntry(root_hash=digest, label="Known raw timestamp"),))
    report = selected.inspect(digest, CODEC, objects, raws, clock=lambda: datetime.now(UTC))
    assert report.metadata.backtest_eligible is False
    assert report.metadata.ineligibility_reasons == (
        "REPLAY_ONLY_CONTRACT",
        "CONTEXT_AVAILABILITY_UNPROVEN",
    )
    with pytest.raises(ValueError, match="timezone-aware"):
        selected.inspect(digest, CODEC, objects, raws, clock=lambda: datetime(2026, 1, 1))
    index = decode_root(root)
    wrong = encode_root(replace(index, raw=replace(index.raw, sha256="a" * 64)))
    objects.get.side_effect = None
    objects.get.return_value = wrong
    with pytest.raises(ValueError, match="trusted hash"):
        selected.list(objects)
    ordered = DatasetCatalog(
        (CatalogEntry(root_hash="b" * 64, label="B"), CatalogEntry(root_hash="a" * 64, label="A"))
    )
    assert [e.label for e in ordered.entries] == ["A", "B"]
