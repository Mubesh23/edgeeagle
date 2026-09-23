"""Operator reports remain private and failures never become successful exercises."""

import json
import runpy
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from edgeeagle_persistence import recovery_cli


def workspace(path: Path, monkeypatch: pytest.MonkeyPatch) -> Mock:
    (path / "compose.yaml").write_text("authored")
    (path / "AGENTS.md").write_text("authored")
    monkeypatch.chdir(path)
    local = Mock()
    local.export.return_value = ({}, ())
    local.database_state.return_value = {"count": 1}
    local.object_state.return_value = []
    local.preflight.return_value = {"system": "one"}
    monkeypatch.setattr(recovery_cli, "LocalRecovery", lambda *args, **kwargs: local)
    monkeypatch.setattr(
        recovery_cli,
        "backup",
        lambda *args: {
            "inventory_sha256": "a" * 64,
            "source_state": {"count": 1},
            "source_objects": [],
            "versions": {"system": "one"},
        },
    )
    monkeypatch.setattr(
        recovery_cli, "verify_restore", lambda *args: args[-1].update(verified=True)
    )
    return local


@pytest.mark.parametrize("mode", ["exercise", "verify", "source-change", "restore-failure"])
def test_private_reports_and_failure_exit_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    local = workspace(tmp_path, monkeypatch)
    args = ["exercise", "--name", "authored", "--bucket", "source", "--root", "b" * 64]
    if mode == "verify":
        args = [
            "verify",
            "--name",
            "authored",
            "--inventory-sha256",
            "a" * 64,
            "--trusted-local-backup",
        ]
    elif mode == "source-change":
        local.database_state.return_value = {"count": 2}
    elif mode == "restore-failure":
        monkeypatch.setattr(
            recovery_cli, "verify_restore", Mock(side_effect=OSError("restore failed"))
        )
    assert recovery_cli.main(args) == (1 if mode in {"source-change", "restore-failure"} else 0)
    reports = list((tmp_path / ".data/recovery").glob("*-verification.json"))
    assert len(reports) == 1 and reports[0].stat().st_mode & 0o777 == 0o600
    report = json.loads(reports[0].read_bytes())
    assert report["status"] == ("incomplete" if "error" in report else "verified")
    if mode == "exercise":
        assert report["source_preserved"] is True


def test_invalid_names_missing_trust_and_wrong_workspace_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        recovery_cli.main(["verify", "--name", "../escape"])
    with pytest.raises(SystemExit):
        recovery_cli.main(["verify", "--name", "valid", "--inventory-sha256", "a" * 64])
    with pytest.raises(ValueError, match="repository root"):
        recovery_cli.main(
            ["verify", "--name", "valid", "--inventory-sha256", "a" * 64, "--trusted-local-backup"]
        )


@pytest.mark.parametrize("unsafe", ["symlink", "permissions"])
def test_unsafe_output_parent_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, unsafe: str
) -> None:
    workspace(tmp_path, monkeypatch)
    if unsafe == "symlink":
        (tmp_path / ".data").symlink_to(tmp_path)
    else:
        (tmp_path / ".data/recovery").mkdir(parents=True, mode=0o755)
    with pytest.raises(ValueError):
        recovery_cli.main(
            ["verify", "--name", "valid", "--inventory-sha256", "a" * 64, "--trusted-local-backup"]
        )


def test_module_entrypoint_help(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["recovery_cli", "--help"])
    with pytest.raises(SystemExit) as result:
        runpy.run_path(recovery_cli.__file__, run_name="__main__")
    assert result.value.code == 0
