"""Private archive framing rejects unsafe or incomplete local recovery sets."""

import json
from pathlib import Path

import pytest

from edgeeagle_ingestion.season_bundle import content_hash
from edgeeagle_persistence.recovery_archive import _private_file, load_archive, write_archive
from tests.unit.test_dataset_manifest import CODEC
from tests.unit.test_season_recovery import exported


def archive(path: Path) -> str:
    files, root = exported()
    return write_archive(path, files, b"PGDMPsynthetic-not-a-real-dump", root, CODEC)


def test_private_archive_roundtrip_and_no_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "private"
    digest = archive(path)
    files, dump, root = load_archive(path, digest, CODEC)
    assert len(files) == 4 and dump.startswith(b"PGDMP") and len(root) == 64
    assert path.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in path.iterdir())
    with pytest.raises(FileExistsError):
        archive(path)


@pytest.mark.parametrize(
    "failure", ["extra", "missing", "corrupt", "marker", "inventory", "symlink", "directory"]
)
def test_reject_unsafe_members(tmp_path: Path, failure: str) -> None:
    path = tmp_path / "private"
    digest = archive(path)
    if failure == "extra":
        (path / "unapproved.env").write_bytes(b"bad")
    elif failure == "missing":
        (path / "raw.bin").unlink()
    elif failure == "corrupt":
        (path / "raw.bin").write_bytes(b"bad")
    elif failure == "marker":
        (path / "COMPLETE").write_bytes(b"bad")
    elif failure == "inventory":
        (path / "inventory.json").write_bytes(b"{}")
    else:
        (path / "raw.bin").unlink()
        if failure == "symlink":
            (path / "raw.bin").symlink_to(path / "database.dump")
        else:
            (path / "raw.bin").mkdir()
    with pytest.raises((ValueError, OSError)):
        load_archive(path, digest, CODEC)


def test_invalid_backup_never_creates_completion_marker(tmp_path: Path) -> None:
    files, root = exported()
    for dump in (b"not a dump", b""):
        with pytest.raises(ValueError):
            write_archive(tmp_path / "invalid", files, dump, root, CODEC)
        assert not (tmp_path / "invalid" / "COMPLETE").exists()


def test_inventory_is_not_a_path_authority(tmp_path: Path) -> None:
    path = tmp_path / "private"
    archive(path)
    value = json.loads((path / "inventory.json").read_bytes())
    value["members"]["../escape"] = value["members"].pop("raw.bin")
    body = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    (path / "inventory.json").write_bytes(body)
    digest = content_hash(body)
    (path / "COMPLETE").write_text(digest)
    with pytest.raises(ValueError):
        load_archive(path, digest, CODEC)


@pytest.mark.parametrize("body", [b"[]", b"{", b"{}"])
def test_invalid_inventory_with_matching_hash(tmp_path: Path, body: bytes) -> None:
    path = tmp_path / "private"
    archive(path)
    (path / "inventory.json").write_bytes(body)
    digest = content_hash(body)
    (path / "COMPLETE").write_text(digest)
    with pytest.raises(ValueError, match="invalid recovery inventory"):
        load_archive(path, digest, CODEC)


def test_private_permissions_bounds_and_symlink_directory(tmp_path: Path) -> None:
    path = tmp_path / "private"
    digest = archive(path)
    with pytest.raises(ValueError, match="size"):
        _private_file(path / "raw.bin", 1)
    (path / "raw.bin").chmod(0o644)
    with pytest.raises(ValueError, match="permissions"):
        load_archive(path, digest, CODEC)
    path.chmod(0o755)
    with pytest.raises(ValueError, match="private owned"):
        load_archive(path, digest, CODEC)
    link = tmp_path / "linked"
    link.symlink_to(path, target_is_directory=True)
    with pytest.raises(ValueError, match="private owned"):
        load_archive(link, digest, CODEC)


def test_failed_write_leaves_no_completion_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from edgeeagle_persistence import recovery_archive

    files, root = exported()
    original = recovery_archive.write_private

    def fail(path: Path, body: bytes) -> None:
        if path.name == "inventory.json":
            raise OSError("disk full")
        original(path, body)

    monkeypatch.setattr(recovery_archive, "write_private", fail)
    with pytest.raises(OSError, match="disk full"):
        write_archive(tmp_path / "incomplete", files, b"PGDMPsynthetic", root, CODEC)
    assert not (tmp_path / "incomplete" / "COMPLETE").exists()


def test_file_change_during_read_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os
    from types import SimpleNamespace

    path = tmp_path / "growing"
    path.write_bytes(b"test")
    path.chmod(0o600)
    metadata = path.stat()
    monkeypatch.setattr(
        os,
        "fstat",
        lambda _: SimpleNamespace(
            st_mode=metadata.st_mode, st_uid=metadata.st_uid, st_nlink=1, st_size=3
        ),
    )
    with pytest.raises(ValueError, match="changed during read"):
        _private_file(path, 10)
