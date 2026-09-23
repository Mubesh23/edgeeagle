"""HTTP catalog uses disposable authored Floci artifacts, never private captures."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from mypy_boto3_s3 import S3Client

from edgeeagle_api.local_datasets import create_local_dataset_app
from edgeeagle_ingestion.season_bundle import build_bundle, decode_root
from edgeeagle_persistence.raw import S3RawPayloadStore
from edgeeagle_persistence.season_storage import S3SeasonObjectStore
from tests.integration.test_raw_storage import raw_bucket as raw_bucket
from tests.unit.test_dataset_manifest import CODEC
from tests.unit.test_season_bundle import values


def test_dataset_api_fresh_replay_and_artifact_loss(
    raw_bucket: tuple[S3Client, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, bucket = raw_bucket
    raw, candidates = values(65)
    root, pages = build_bundle(raw.reference(), candidates, CODEC)
    objects = S3SeasonObjectStore(client, bucket, CODEC)
    S3RawPayloadStore(client, bucket).put(raw)
    for page in pages:
        objects.put(page)
    digest = objects.put(root)
    before = client.list_objects_v2(Bucket=bucket)["Contents"]
    monkeypatch.chdir(tmp_path)
    config = tmp_path / ".data/catalog.json"
    config.parent.mkdir()
    config.write_text(
        json.dumps(
            {"format": 1, "bucket": bucket, "entries": [{"root_hash": digest, "label": "Authored"}]}
        )
    )
    monkeypatch.setenv("EDGEEAGLE_DATASET_CATALOG", str(config))
    with TestClient(create_local_dataset_app()) as http:
        assert http.get("/v1/datasets").json()["items"][0]["replay_status"] == "NOT_CHECKED"
        path = f"/v1/datasets/{digest}/inspection"
        response = http.get(path)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        report = response.json()
        assert report["receipt_count"] == 65
        assert report["metadata"]["backtest_eligible"] is False
        assert report["metadata"]["raw"]["capture"]["available_at"] is None
        assert report["replay_status"] == "VERIFIED"
        assert report["database_acceptance_verified"] is False
        assert http.get(path).json()["replay_completed_at"] != report["replay_completed_at"]
        assert client.list_objects_v2(Bucket=bucket)["Contents"] == before
        page_hash = decode_root(root).page_hashes[-1]
        client.delete_object(
            Bucket=bucket, Key=f"snapshots/football-data-seasons/v1/{page_hash}.json"
        )
        assert http.get("/v1/datasets").status_code == 200
        failed = http.get(path)
        assert failed.status_code == 503
        assert bucket not in failed.text and "VERIFIED" not in failed.text
        assert objects.get(digest) == root
