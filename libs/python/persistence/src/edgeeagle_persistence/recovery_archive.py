"""ADR-030 bounded private local archive, not an untrusted SQL import format."""

import json
import os
import stat
from pathlib import Path

from edgeeagle_ingestion.manifests import EventReceiptCodec
from edgeeagle_ingestion.season_bundle import content_hash, validate_digest
from edgeeagle_ingestion.season_recovery import verify_season

MAX_DUMP_BYTES = 64 * 1024 * 1024
LIMITS = {
    "root.json": 65_536,
    "raw.bin": 1_048_576,
    **{f"page-{i:02}.json": 1_048_576 for i in range(8)},
    "database.dump": MAX_DUMP_BYTES,
    "inventory.json": 16_384,
    "COMPLETE": 64,
}


def _inventory(files: dict[str, bytes], root: str) -> bytes:
    return json.dumps(
        {
            "format": 1,
            "root": root,
            "usage": "REPLAY_ONLY",
            "members": {
                name: {"size": len(body), "sha256": content_hash(body)}
                for name, body in files.items()
            },
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _check_dump(dump: bytes) -> None:
    if len(dump) > MAX_DUMP_BYTES or not dump.startswith(b"PGDMP"):
        raise ValueError("expected a bounded PostgreSQL custom-format dump")


def write_private(path: Path, body: bytes) -> None:
    """Exclusive creation; never truncate an existing file or follow its symlink."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(body)
        stream.flush()
        os.fsync(stream.fileno())


def write_archive(
    path: Path,
    files: dict[str, bytes],
    dump: bytes,
    root: str,
    codec: EventReceiptCodec,
) -> str:
    """Create a new private directory; only a fully written archive is complete."""
    verify_season(files, root, codec)
    _check_dump(dump)
    bodies = files | {"database.dump": dump}
    inventory = _inventory(bodies, root)
    path.mkdir(mode=0o700)
    for name, body in bodies.items():
        write_private(path / name, body)
    write_private(path / "inventory.json", inventory)
    digest = content_hash(inventory)
    write_private(path / "COMPLETE", digest.encode())
    return digest


def _private_file(path: Path, limit: int) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_mode & 0o077
            or metadata.st_uid != os.getuid()
            or metadata.st_nlink != 1
            or metadata.st_size > limit
        ):
            raise ValueError("unsafe archive member type, permissions, links or size")
        body = stream.read(limit + 1)
        if len(body) != metadata.st_size or len(body) > limit:
            raise ValueError("archive member changed during read")
        return body


def load_archive(
    path: Path, inventory_hash: str, codec: EventReceiptCodec
) -> tuple[dict[str, bytes], bytes, str]:
    """Load all bytes before destination I/O; caller supplies separately retained hash."""
    validate_digest(inventory_hash)
    metadata = path.lstat()
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_mode & 0o077
        or metadata.st_uid != os.getuid()
    ):
        raise ValueError("archive must be a private owned directory, not a symlink")
    names = {p.name for p in path.iterdir()}
    if not names <= LIMITS.keys() or not {"inventory.json", "COMPLETE", "database.dump"} <= names:
        raise ValueError("unexpected or missing archive members")
    bodies = {name: _private_file(path / name, LIMITS[name]) for name in names}
    inventory = bodies.pop("inventory.json")
    if (
        content_hash(inventory) != inventory_hash
        or bodies.pop("COMPLETE") != inventory_hash.encode()
    ):
        raise ValueError("archive is incomplete or differs from trusted inventory hash")
    try:
        root = json.loads(inventory)["root"]
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError("invalid recovery inventory") from error
    if _inventory(bodies, root) != inventory:
        raise ValueError("inventory bytes, member sizes or hashes differ")
    dump = bodies.pop("database.dump")
    _check_dump(dump)
    verify_season(bodies, root, codec)
    return bodies, dump, root
