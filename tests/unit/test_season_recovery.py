"""Portable recovery must fail before writes and retain canonical identity."""

from dataclasses import replace
from unittest.mock import Mock

import pytest

from edgeeagle_ingestion.football_data import MAX_CSV_BYTES
from edgeeagle_ingestion.season_bundle import build_bundle, content_hash, decode_root, encode_root
from edgeeagle_ingestion.season_recovery import (
    _Objects,
    _Raw,
    export_season,
    restore_season,
    verify_season,
)
from tests.unit.test_dataset_manifest import CODEC
from tests.unit.test_season_bundle import values


def exported() -> tuple[dict[str, bytes], str]:
    raw, candidates = values(65)
    root, pages = build_bundle(raw.reference(), candidates, CODEC)
    objects, raws = Mock(), Mock()
    objects.get.side_effect = {content_hash(b): b for b in (root, *pages)}.get
    raws.get.return_value = raw.body
    files = export_season(content_hash(root), CODEC, objects, raws)
    objects.put.assert_not_called()
    raws.put.assert_not_called()
    return files, content_hash(root)


def test_export_verify_restore_preserves_root_and_writes_root_last() -> None:
    files, digest = exported()
    assert set(files) == {"root.json", "page-00.json", "page-01.json", "raw.bin"}
    candidates = verify_season(files, digest, CODEC)
    assert len(candidates) == 65
    calls = Mock()
    calls.raw.put.side_effect = lambda payload: payload.reference()
    calls.objects.put.side_effect = content_hash
    assert restore_season(files, digest, CODEC, calls.objects, calls.raw) == candidates
    assert calls.mock_calls[0][0] == "raw.put"
    assert calls.mock_calls[-1].args == (files["root.json"],)


@pytest.mark.parametrize("failure", ["missing", "extra", "raw", "page", "root", "hash"])
def test_invalid_archive_never_writes(failure: str) -> None:
    files, digest = exported()
    if failure == "missing":
        del files["page-01.json"]
    elif failure == "extra":
        files["../escape"] = b"bad"
    elif failure == "hash":
        digest = "bad"
    else:
        name = {"raw": "raw.bin", "page": "page-01.json", "root": "root.json"}[failure]
        files[name] += b"x"
    objects, raws = Mock(), Mock()
    with pytest.raises((ValueError, FileNotFoundError)):
        restore_season(files, digest, CODEC, objects, raws)
    objects.put.assert_not_called()
    raws.put.assert_not_called()


@pytest.mark.parametrize("missing", ["root", "page", "raw"])
def test_export_missing_member(missing: str) -> None:
    files, digest = exported()
    index = decode_root(files["root.json"])
    objects, raws = Mock(), Mock()
    bodies = {digest: files["root.json"]} | {
        key: files[f"page-{i:02}.json"] for i, key in enumerate(index.page_hashes)
    }
    if missing != "raw":
        bodies.pop(digest if missing == "root" else index.page_hashes[-1])
    objects.get.side_effect = bodies.get
    raws.get.return_value = None if missing == "raw" else files["raw.bin"]
    with pytest.raises(FileNotFoundError):
        export_season(digest, CODEC, objects, raws)


@pytest.mark.parametrize("bad_ack", ["raw", "page", "root"])
def test_bad_acknowledgements_fail_without_publishing_root(bad_ack: str) -> None:
    files, digest = exported()
    objects, raws = Mock(), Mock()
    raws.put.side_effect = lambda payload: None if bad_ack == "raw" else payload.reference()
    objects.put.side_effect = lambda body: (
        "0" * 64 if (body == files["root.json"]) == (bad_ack == "root") else content_hash(body)
    )
    with pytest.raises(ValueError, match="acknowledgement"):
        restore_season(files, digest, CODEC, objects, raws)
    if bad_ack != "root":
        assert all(call.args != (files["root.json"],) for call in objects.put.call_args_list)


def test_bounds_and_read_only_replay_ports() -> None:
    files, digest = exported()
    files["raw.bin"] = b"x" * (MAX_CSV_BYTES + 1)
    with pytest.raises(ValueError, match="byte limit"):
        verify_season(files, digest, CODEC)
    index = decode_root(files["root.json"])
    root = encode_root(replace(index, raw=replace(index.raw, size_bytes=MAX_CSV_BYTES + 1)))
    objects, raws = Mock(), Mock()
    objects.get.return_value = root
    with pytest.raises(ValueError, match="byte limit"):
        export_season(content_hash(root), CODEC, objects, raws)
    raws.get.assert_not_called()
    raw, _ = values(1)
    with pytest.raises(NotImplementedError, match="read-only"):
        _Raw(raw).put(raw)
    with pytest.raises(NotImplementedError, match="read-only"):
        _Objects({}).put(b"bad")
