"""Bounded, canonical pages pin a complete capture, not independently replayable slices."""

import hashlib
import json
from contextlib import contextmanager
from dataclasses import replace
from typing import Any
from unittest.mock import Mock

import pytest

from edgeeagle_ingestion.football_data import normalize_season_results
from edgeeagle_ingestion.season_bundle import (
    MAX_PAGE_BYTES,
    MAX_ROOT_BYTES,
    SeasonIndex,
    build_bundle,
    decode_page,
    decode_root,
    encode_page,
    validate_object,
    verify_bundle,
)
from tests.unit.test_dataset_manifest import CODEC
from tests.unit.test_fixture_references import NOW
from tests.unit.test_football_data import normalized
from tests.unit.test_football_data_season import season_batch, season_resolver


def values(count: int = 380) -> Any:
    raw, requests = season_batch(count)
    store = Mock()
    store.get.return_value = raw.body

    @contextmanager
    def reads() -> Any:
        yield season_resolver()

    return raw, normalize_season_results(store, raw.reference(), requests, reads, as_of=NOW)


@pytest.mark.parametrize("count,pages", [(1, 1), (64, 1), (65, 2), (380, 6), (512, 8)])
def test_bundle_round_trip_and_complete_read_only_replay(count: int, pages: int) -> None:
    raw, candidates = values(count)
    root, bodies = build_bundle(raw.reference(), candidates, CODEC)
    assert build_bundle(raw.reference(), tuple(reversed(candidates)), CODEC) == (root, bodies)
    index = decode_root(root)
    assert index.row_count == count
    assert len(bodies) == pages
    assert index.page_hashes == tuple(hashlib.sha256(body).hexdigest() for body in bodies)
    assert [len(decode_page(body, CODEC)) for body in bodies] == [64] * (pages - 1) + [
        count - 64 * (pages - 1)
    ]
    store, raw_store = Mock(), Mock()
    store.get.side_effect = dict(zip(index.page_hashes, bodies, strict=True)).get
    raw_store.get.return_value = raw.body
    assert verify_bundle(root, CODEC, store, raw_store) == candidates
    raw_store.get.assert_called_once_with(raw.reference())
    store.put.assert_not_called()
    raw_store.put.assert_not_called()


@pytest.mark.parametrize("failure", ["missing", "corrupt", "duplicate", "count", "order"])
def test_bundle_fails_before_raw_io_for_invalid_final_page_or_membership(failure: str) -> None:
    raw, candidates = values(65)
    root, bodies = build_bundle(raw.reference(), candidates, CODEC)
    index = decode_root(root)
    store, raw_store = Mock(), Mock()
    objects = dict(zip(index.page_hashes, bodies, strict=True))
    if failure == "missing":
        objects.pop(index.page_hashes[-1])
    elif failure == "corrupt":
        objects[index.page_hashes[-1]] = bodies[-1] + b" "
    else:
        model = json.loads(root)
        if failure == "duplicate":
            model["page_hashes"][1] = model["page_hashes"][0]
        elif failure == "count":
            model["row_count"] += 1
        else:
            model["page_hashes"].reverse()
        root = json.dumps(model, sort_keys=True, separators=(",", ":")).encode()
    store.get.side_effect = objects.get
    with pytest.raises((ValueError, FileNotFoundError)):
        verify_bundle(root, CODEC, store, raw_store)
    raw_store.get.assert_not_called()


@pytest.mark.parametrize("failure", ["raw", "duplicate", "legacy", "oversize"])
def test_bundle_builder_rejects_invalid_receipts(failure: str) -> None:
    raw, candidates = values(2)
    if failure == "raw":
        raw = replace(raw, body=raw.body + b" ")
    elif failure == "duplicate":
        candidates = (candidates[0], candidates[0])
    elif failure == "legacy":
        candidates = normalized()
    else:
        candidates = (replace(candidates[0], context_version="x" * MAX_PAGE_BYTES),)
    with pytest.raises(ValueError):
        build_bundle(raw.reference(), candidates, CODEC)


def test_strict_codecs_and_root_before_any_storage_access() -> None:
    raw, candidates = values(1)
    root, pages = build_bundle(raw.reference(), candidates, CODEC)
    for body in (
        root + b" ",
        b"x" * (MAX_ROOT_BYTES + 1),
        root.replace(b'"format":1', b'"format":true'),
    ):
        store, raw_store = Mock(), Mock()
        with pytest.raises(ValueError):
            verify_bundle(body, CODEC, store, raw_store)
        store.get.assert_not_called()
        raw_store.get.assert_not_called()
    for body in (pages[0] + b" ", b"x" * (MAX_PAGE_BYTES + 1), b'{"format":1,"format":1}'):
        with pytest.raises(ValueError):
            decode_page(body, CODEC)


def test_storage_validation_and_invalid_value_bounds() -> None:
    raw, candidates = values(1)
    root, pages = build_bundle(raw.reference(), candidates, CODEC)
    for body in (root, *pages):
        assert validate_object(body, CODEC) == hashlib.sha256(body).hexdigest()
    for body in (b"[]", b"null", b'{"kind":"unknown"}', b'{"a":NaN}', b'{"a":1.0}'):
        with pytest.raises(ValueError):
            validate_object(body, CODEC)
    for count, hashes in ((True, ("a" * 64,)), (513, ("a" * 64,)), (1, ()), (1, ("bad",))):
        with pytest.raises(ValueError):
            SeasonIndex(raw=raw.reference(), row_count=count, page_hashes=hashes)
    with pytest.raises(ValueError):
        build_bundle(raw.reference(), (), CODEC)
    with pytest.raises(ValueError):
        encode_page((), CODEC)
    page = json.loads(pages[0])
    page["receipts"][0]["receipt_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        decode_page(json.dumps(page, sort_keys=True, separators=(",", ":")).encode(), CODEC)
