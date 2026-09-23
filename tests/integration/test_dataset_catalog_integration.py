"""Disposable Floci catalog listing/inspection uses authored captures only."""

import json
from pathlib import Path

import pytest
from mypy_boto3_s3 import S3Client

from edgeeagle_ingestion.dataset_catalog import CatalogEntry, DatasetCatalog
from edgeeagle_ingestion.season_bundle import build_bundle, content_hash, decode_root
from edgeeagle_persistence import dataset_cli
from edgeeagle_persistence.raw import S3RawPayloadStore
from edgeeagle_persistence.season_storage import S3SeasonObjectStore
from tests.integration.test_raw_storage import raw_bucket as raw_bucket
from tests.unit.test_dataset_manifest import CODEC
from tests.unit.test_season_bundle import values


def test_catalog_cli_retained_replay_without_database_or_writes(
    raw_bucket: tuple[S3Client, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
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
    path = tmp_path / ".data/catalog.json"
    path.parent.mkdir()
    path.write_text(
        json.dumps(
            {
                "format": 1,
                "bucket": bucket,
                "entries": [{"root_hash": digest, "label": "Authored season"}],
            }
        )
    )
    assert dataset_cli.main(["--catalog", str(path), "list"]) == 0
    assert json.loads(capsys.readouterr().out)["items"][0]["replay_status"] == "NOT_CHECKED"
    assert dataset_cli.main(["--catalog", str(path), "inspect", digest]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["receipt_count"] == 65 and report["participant_count"] == 2
    assert report["metadata"]["backtest_eligible"] is False
    assert client.list_objects_v2(Bucket=bucket)["Contents"] == before
    # Deliberate loss of a test-owned page. Metadata remains readable, but replay fails.
    page_hash = decode_root(root).page_hashes[-1]
    client.delete_object(Bucket=bucket, Key=f"snapshots/football-data-seasons/v1/{page_hash}.json")
    assert dataset_cli.main(["--catalog", str(path), "list"]) == 0
    assert json.loads(capsys.readouterr().out)["items"][0]["replay_status"] == "NOT_CHECKED"
    assert dataset_cli.main(["--catalog", str(path), "inspect", digest]) == 1
    assert not capsys.readouterr().out
    assert objects.get(digest) == root and content_hash(root) == digest
    selected = DatasetCatalog((CatalogEntry(root_hash=digest, label="Authored"),))
    assert selected.list(objects)[0].metadata.declared_row_count == 65
