"""Distinct CSV snapshot kind with unchanged synthetic manifest compatibility."""

import json
from dataclasses import replace
from unittest.mock import Mock

import pytest

from edgeeagle_ingestion.manifests import (
    ManifestCapture,
    ReplayDatasetManifest,
    decode_manifest,
    encode_manifest,
)
from edgeeagle_ingestion.snapshot_replay import verify_manifest
from tests.unit.test_dataset_manifest import CODEC, manifest
from tests.unit.test_football_data import csv_payload, normalized


def test_csv_manifest_roundtrip_and_replay() -> None:
    values = normalized()
    model = ReplayDatasetManifest(captures=(ManifestCapture(raw=values[0].raw, candidates=values),))
    body = encode_manifest(model, CODEC)
    assert json.loads(body)["manifest"]["kind"] == "FOOTBALL_DATA_RESULTS_REPLAY"
    assert json.loads(body)["manifest"]["usage"] == "REPLAY_ONLY"
    assert decode_manifest(body, CODEC) == model
    store = Mock()
    store.get.return_value = csv_payload().body
    assert verify_manifest(body, CODEC, store) == (values,)
    assert (
        encode_manifest(
            ReplayDatasetManifest(
                captures=(ManifestCapture(raw=values[0].raw, candidates=tuple(reversed(values))),)
            ),
            CODEC,
        )
        == body
    )
    assert values[0].soccer_result is not None
    changed = replace(values[0], soccer_result=replace(values[0].soccer_result, home_goals=3))
    changed_body = encode_manifest(
        ReplayDatasetManifest(
            captures=(ManifestCapture(raw=changed.raw, candidates=(changed, values[1])),)
        ),
        CODEC,
    )
    assert json.loads(changed_body)["dataset_version"] != json.loads(body)["dataset_version"]
    with pytest.raises(ValueError, match="reproduce"):
        verify_manifest(changed_body, CODEC, store)


def test_no_mixed_kinds_or_empty_csv_groups() -> None:
    values = normalized()
    capture = ManifestCapture(raw=values[0].raw, candidates=values)
    for other in (
        manifest().captures[0],
        ManifestCapture(raw=replace(values[0].raw, sha256="a" * 64), candidates=()),
    ):
        with pytest.raises(ValueError):
            ReplayDatasetManifest(captures=(capture, other))
    with pytest.raises(ValueError):
        ManifestCapture(
            raw=values[0].raw, candidates=(replace(values[0], normalizer_version="unsupported"),)
        )


def test_wrong_kind_is_not_repaired_before_raw_reads() -> None:
    values = normalized()
    body = encode_manifest(
        ReplayDatasetManifest(captures=(ManifestCapture(raw=values[0].raw, candidates=values),)),
        CODEC,
    )
    store = Mock()
    with pytest.raises(ValueError):
        verify_manifest(
            body.replace(b"FOOTBALL_DATA_RESULTS_REPLAY", b"MAPPED_EVENT_REPLAY"), CODEC, store
        )
    store.get.assert_not_called()
