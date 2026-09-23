"""Operator workflow failure boundaries use no network or Docker."""

import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock

import psycopg
import pytest

from edgeeagle_persistence import local_recovery
from edgeeagle_persistence.local_recovery import (
    LocalRecovery,
    _bucket,
    _database,
    backup,
    verify_restore,
)
from tests.unit.test_recovery_archive import archive


def test_corrupt_archive_never_contacts_destination(tmp_path: Path) -> None:
    path = tmp_path / "backup"
    digest = archive(path)
    (path / "raw.bin").write_bytes(b"corrupt")
    local = Mock()
    with pytest.raises(ValueError):
        verify_restore(local, path, digest)
    assert local.mock_calls == []


def test_failed_dump_never_publishes_backup(tmp_path: Path) -> None:
    local = Mock()
    local.export.return_value = ({}, ())
    local.dump.side_effect = OSError("dump failed")
    with pytest.raises(OSError, match="dump failed"):
        backup(local, tmp_path / "backup", "edgeeagle", "source", "a" * 64)
    assert not (tmp_path / "backup" / "COMPLETE").exists()


@pytest.mark.parametrize(
    "value", ["postgres", "remote/db", "edgeeagle; DROP DATABASE", "edgeeagle_recovery_bad"]
)
def test_database_target_allowlist(value: str) -> None:
    with pytest.raises(ValueError):
        _database(value)


@pytest.mark.parametrize("value", ["production", "s3://edgeeagle", "edgeeagle-recovery-../bad"])
def test_bucket_target_allowlist(value: str) -> None:
    with pytest.raises(ValueError):
        _bucket(value)


def test_ports_preflight_and_active_target_guards(tmp_path: Path) -> None:
    for port in (0, 65536, True):
        with pytest.raises(ValueError):
            LocalRecovery(tmp_path, postgres_port=port)
    local = LocalRecovery(tmp_path)
    with pytest.raises(RuntimeError, match="preflight"):
        local._pg(["pg_dump", "--version"])
    with pytest.raises(ValueError, match="isolated"):
        local.restore("edgeeagle", "source", b"", {}, "a" * 64)
    local._owned = ("already", "active")
    with pytest.raises(RuntimeError, match="already active"), local.isolated({}):
        pass


def test_pg_version_omits_connection_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = Mock(return_value=b"version")
    monkeypatch.setattr(local_recovery, "_run", run)
    local = LocalRecovery(tmp_path)
    local.docker = ["docker", "exec", "postgres"]
    assert local._pg(["pg_dump", "--version"]) == b"version"
    run.assert_called_once_with(["docker", "exec", "postgres", "pg_dump", "--version"])


@pytest.mark.parametrize("failure", ["database", "collision", "bucket", "body", "cleanup", "none"])
def test_owned_cleanup_never_deletes_uncreated_resources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    local = LocalRecovery(tmp_path)
    client, admin = Mock(), Mock()
    client.list_buckets.return_value = {"Buckets": []}
    if failure == "database":
        admin.execute.side_effect = OSError("create failed")
    if failure == "bucket":
        client.create_bucket.side_effect = OSError("create failed")
    if failure == "cleanup":
        client.delete_bucket.side_effect = OSError("cleanup failed")
    suffix = "a" * 32
    monkeypatch.setattr(local_recovery, "uuid4", lambda: Mock(hex=suffix))
    if failure == "collision":
        client.list_buckets.return_value = {"Buckets": [{"Name": f"edgeeagle-recovery-{suffix}"}]}

    @contextmanager
    def connect() -> Any:
        yield admin

    monkeypatch.setattr(local, "connect", connect)
    monkeypatch.setattr(local, "client", lambda: client)
    monkeypatch.setattr(local, "object_state", lambda _: [{"key": "owned"}])
    report: dict[str, Any] = {}

    def exercise() -> None:
        with local.isolated(report) as pair:
            assert local._owned == pair
            if failure == "body":
                raise OSError("restore failed")

    if failure == "none":
        exercise()
    else:
        with pytest.raises((OSError, FileExistsError)):
            exercise()
    assert local._owned is None
    client.close.assert_called_once()
    assert report["database_removed"] is (failure != "database")
    assert report["bucket_removed"] is (failure in {"body", "none"})
    if failure in {"database", "collision", "bucket"}:
        client.delete_object.assert_not_called()
        client.delete_bucket.assert_not_called()
    if failure == "database":
        assert admin.execute.call_count == 1
    else:
        assert admin.execute.call_count == 2


def test_remote_docker_and_mismatched_postgres_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local = LocalRecovery(tmp_path)
    monkeypatch.delenv("DOCKER_CONTEXT", raising=False)
    monkeypatch.setenv("DOCKER_HOST", "tcp://remote:2375")
    with pytest.raises(ValueError, match="Unix-socket"):
        local.preflight()
    monkeypatch.setenv("DOCKER_HOST", "unix:///local.sock")
    monkeypatch.setattr(local_recovery, "_run", lambda *args: b"server-one")
    admin = Mock()
    admin.execute.return_value.fetchone.return_value = ("different-server",)

    @contextmanager
    def connect() -> Any:
        yield admin

    monkeypatch.setattr(local, "connect", connect)
    with pytest.raises(ValueError, match="does not match"):
        local.preflight()


def test_source_change_or_existing_path_does_not_publish(tmp_path: Path) -> None:
    local = Mock()
    with pytest.raises(FileExistsError):
        backup(local, tmp_path, "edgeeagle", "source", "a" * 64)
    local.preflight.assert_not_called()
    local.export.return_value = ({}, ())
    local.database_state.side_effect = [{"count": 1}, {"count": 2}]
    with pytest.raises(ValueError, match="source changed"):
        backup(local, tmp_path / "backup", "edgeeagle", "source", "a" * 64)
    assert not (tmp_path / "backup").exists()


def test_restore_artifact_mismatch_is_not_success(tmp_path: Path) -> None:
    path = tmp_path / "backup"
    digest = archive(path)
    local = Mock()

    @contextmanager
    def isolated(report: dict[str, Any]) -> Any:
        yield "target-db", "target-bucket"

    local.isolated.side_effect = isolated
    local.export.return_value = ({}, ())
    report: dict[str, Any] = {}
    with pytest.raises(ValueError, match="artifact bytes"):
        verify_restore(local, path, digest, report)
    assert report["verified"] is False


def test_command_output_bound_and_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def run(arguments: list[str], **kwargs: Any) -> None:
        assert kwargs["timeout"] == 60 and kwargs["check"] is True
        assert "DOCKER_HOST" not in kwargs["env"]
        kwargs["stdout"].write(b"too long")

    monkeypatch.setenv("DOCKER_HOST", "tcp://remote")
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(local_recovery, "MAX_DUMP_BYTES", 3)
    with pytest.raises(ValueError, match="output exceeds"):
        local_recovery._run(["unused"])
    monkeypatch.setattr(local_recovery, "MAX_DUMP_BYTES", 20)
    assert local_recovery._run(["unused"]) == b"too long"


def test_explicit_context_and_loopback_hostaddr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local = LocalRecovery(tmp_path)
    connection = MagicMock()
    connection.__enter__.return_value.execute.return_value.fetchone.return_value = ("system",)
    connect = Mock(return_value=connection)
    monkeypatch.setattr(psycopg, "connect", connect)
    monkeypatch.setenv("PGHOSTADDR", "192.0.2.1")
    local.connect("edgeeagle")
    assert connect.call_args.kwargs["hostaddr"] == "127.0.0.1"
    monkeypatch.setenv("DOCKER_CONTEXT", "local-test")
    run = Mock(
        side_effect=[b"unix:///local.sock", b"system", b"pg_dump version", b"pg_restore version"]
    )
    monkeypatch.setattr(local_recovery, "_run", run)
    assert local.preflight()["postgres_system_identifier"] == "system"
    assert "local-test" in run.call_args_list[0].args[0]


def test_truncated_object_audit_and_receipt_mismatch_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.unit.test_season_bundle import values

    local = LocalRecovery(tmp_path)
    client = Mock()
    client.list_objects_v2.return_value = {"IsTruncated": True}
    monkeypatch.setattr(local, "client", lambda: client)
    with pytest.raises(ValueError, match="audit limit"):
        local.object_state("edgeeagle-raw-test-authored")
    client.close.assert_called_once()
    engine = MagicMock()
    monkeypatch.setattr(local_recovery, "create_engine", lambda *args, **kwargs: engine)
    repository = Mock()
    repository.get.return_value = None
    monkeypatch.setattr(local_recovery, "PostgresEventAcceptanceRepository", lambda _: repository)
    _, candidates = values(1)
    with pytest.raises(ValueError, match="canonical receipt differs"):
        local.database_state("edgeeagle", candidates)
    engine.dispose.assert_called_once()
