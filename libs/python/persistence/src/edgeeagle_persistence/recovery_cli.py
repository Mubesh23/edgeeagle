"""Private operator command; never invoked by routine acquisition or validation."""

import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from edgeeagle_persistence.local_recovery import LocalRecovery, backup, verify_restore
from edgeeagle_persistence.recovery_archive import write_private


def _name(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", value):
        raise argparse.ArgumentTypeError("use a lowercase local archive name, not a path")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="mode", required=True)
    exercise = modes.add_parser("exercise", help="back up, restore, verify, clean owned targets")
    exercise.add_argument("--name", required=True, type=_name)
    exercise.add_argument("--database", default="edgeeagle")
    exercise.add_argument("--bucket", required=True)
    exercise.add_argument("--root", required=True)
    verify = modes.add_parser("verify", help="repeat isolated verification from a retained backup")
    verify.add_argument("--name", required=True, type=_name)
    verify.add_argument("--inventory-sha256", required=True)
    verify.add_argument(
        "--trusted-local-backup",
        required=True,
        action="store_true",
        help="acknowledge this is your trusted dump, not an untrusted SQL archive",
    )
    args = parser.parse_args(argv)
    repository = Path.cwd()
    if not (repository / "compose.yaml").is_file() or not (repository / "AGENTS.md").is_file():
        raise ValueError("run from the EdgeEagle repository root")
    data = repository / ".data"
    parent = data / "recovery"
    if data.is_symlink() or parent.is_symlink():
        raise ValueError("private recovery path must not be a symlink")
    data.mkdir(mode=0o700, exist_ok=True)
    parent.mkdir(mode=0o700, exist_ok=True)
    if parent.stat().st_mode & 0o077:
        raise ValueError("private recovery directory must have owner-only permissions")
    path = parent / args.name
    report_path = parent / f"{args.name}-{uuid4().hex}-verification.json"
    local = LocalRecovery(
        repository,
        postgres_port=int(os.environ.get("EDGEEAGLE_POSTGRES_PORT", "55432")),
        floci_port=int(os.environ.get("EDGEEAGLE_FLOCI_PORT", "4566")),
    )
    report = {
        "mode": args.mode,
        "started_at": datetime.now(UTC).isoformat(),
        "status": "incomplete",
        "archive": str(path),
        "restore": {},
    }
    print(f"Private report: {report_path}", flush=True)
    try:
        if args.mode == "exercise":
            saved = backup(local, path, args.database, args.bucket, args.root)
            # Keep the inventory identity outside the archive before attempting restore.
            write_private(parent / f"{args.name}-backup.json", json.dumps(saved, indent=2).encode())
            report["backup"] = saved
            inventory = saved["inventory_sha256"]
        else:
            inventory = args.inventory_sha256
        verify_restore(local, path, inventory, report["restore"])
        if args.mode == "exercise":
            _, candidates = local.export(args.bucket, args.root)
            if (
                saved["source_state"] != local.database_state(args.database, candidates)
                or saved["source_objects"] != local.object_state(args.bucket)
                or saved["versions"] != local.preflight()
            ):
                raise ValueError("source identity or state changed during recovery exercise")
            report["source_preserved"] = True
        report["status"] = "verified"
        return 0
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        print(f"Recovery failed: {report['error']}", file=sys.stderr)
        return 1
    finally:
        report["finished_at"] = datetime.now(UTC).isoformat()
        write_private(report_path, json.dumps(report, indent=2, sort_keys=True).encode())


if __name__ == "__main__":
    raise SystemExit(main())
