"""Synthetic PostgreSQL dump and Floci restore; never private provider captures."""

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from mypy_boto3_s3 import S3Client
from sqlalchemy import Engine

from edgeeagle_persistence.local_recovery import LocalRecovery, backup, verify_restore
from edgeeagle_persistence.recovery_archive import load_archive, write_archive
from tests.integration.test_raw_storage import raw_bucket as raw_bucket
from tests.integration.test_repositories import repository_engine as repository_engine
from tests.integration.test_season_import import setup_import
from tests.unit.test_dataset_manifest import CODEC


def test_private_recovery_independent_restore_and_owned_cleanup(
    repository_engine: Engine, raw_bucket: tuple[S3Client, str], tmp_path: Path
) -> None:
    _, _, _, _, run = setup_import(
        repository_engine, raw_bucket, tmp_path / "authored.csv", count=65
    )
    root = run()
    local = LocalRecovery(
        Path(__file__).resolve().parents[2],
        postgres_port=int(os.environ.get("EDGEEAGLE_POSTGRES_PORT", "55432")),
        floci_port=int(os.environ.get("EDGEEAGLE_FLOCI_PORT", "4566")),
    )
    source = repository_engine.url.database
    assert source is not None
    bucket = raw_bucket[1]
    path = tmp_path / "backup"
    report = backup(local, path, source, bucket, root)
    # A separate operator instance has no source database/bucket parameters.
    restorer = LocalRecovery(
        local.repository, postgres_port=local.postgres_port, floci_port=local.floci_port
    )
    restored = verify_restore(restorer, path, report["inventory_sha256"])
    assert restored["verified"] is True
    assert restored["database_removed"] is restored["bucket_removed"] is True
    assert restored["restored_state"]["database_oid"] != report["source_state"]["database_oid"]
    assert restored["restored_state"]["counts"] == report["source_state"]["counts"]
    assert restored["restored_state"]["schema"] == report["source_state"]["schema"]
    assert restored["restored_state"]["receipts_verified"] == 65
    assert restored["objects"] == 4
    with local.connect() as admin:
        assert (
            admin.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (restored["target_database"],)
            ).fetchone()
            is None
        )
    assert not any(
        b["Name"] == restored["target_bucket"]
        for b in raw_bucket[0].list_buckets().get("Buckets", [])
    )
    _, candidates = local.export(bucket, root)
    assert local.database_state(source, candidates) == report["source_state"]
    assert local.object_state(bucket) == report["source_objects"]


@pytest.mark.parametrize("failure", ["dump", "receipt"])
def test_private_recovery_failure_cleans_owned_targets(
    repository_engine: Engine,
    raw_bucket: tuple[S3Client, str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
) -> None:
    _, _, _, _, run = setup_import(
        repository_engine, raw_bucket, tmp_path / "authored.csv", count=1
    )
    root = run()
    local = LocalRecovery(
        Path(__file__).resolve().parents[2],
        postgres_port=int(os.environ.get("EDGEEAGLE_POSTGRES_PORT", "55432")),
        floci_port=int(os.environ.get("EDGEEAGLE_FLOCI_PORT", "4566")),
    )
    source = repository_engine.url.database
    assert source is not None
    path = tmp_path / "backup"
    saved = backup(local, path, source, raw_bucket[1], root)
    digest = saved["inventory_sha256"]
    if failure == "dump":
        files, _, root = load_archive(path, digest, CODEC)
        path = tmp_path / "bad-dump"
        digest = write_archive(path, files, b"PGDMPinvalid archive", root, CODEC)
    else:
        original = local.restore

        def corrupt_receipt(
            database: str, bucket: str, dump: bytes, files: dict[str, bytes], root: str
        ) -> None:
            original(database, bucket, dump, files, root)
            with local.connect(database) as connection:
                # Deliberate out-of-band corruption of this test-owned restored copy only.
                # Normal receipt writes/deletes are correctly blocked by the immutable trigger.
                connection.execute("ALTER TABLE event_normalizations DISABLE TRIGGER USER")
                connection.execute("DELETE FROM event_normalizations")
                connection.execute("ALTER TABLE event_normalizations ENABLE TRIGGER USER")

        monkeypatch.setattr(local, "restore", corrupt_receipt)
    report: dict[str, Any] = {}
    with pytest.raises((ValueError, subprocess.CalledProcessError)):
        verify_restore(local, path, digest, report)
    assert report["verified"] is False
    assert report["database_removed"] is report["bucket_removed"] is True
    _, candidates = local.export(raw_bucket[1], root)
    assert local.database_state(source, candidates) == saved["source_state"]
    assert local.object_state(raw_bucket[1]) == saved["source_objects"]
