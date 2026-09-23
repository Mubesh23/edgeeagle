# Private local recovery verification

This operator workflow backs up one retained ADR-029 replay root plus a logical
snapshot of its local PostgreSQL database, restores into isolated local resources,
verifies every canonical receipt, and removes only those exercise-owned resources.
It does not restore over the developer database or promote recovered state into
the application. See [ADR-030](../adr/ADR-030-private-local-recovery.md).

## Run an exercise

Start the existing local services with `scripts/local-up`. Do not remove their
volumes. From repository root, use a new lowercase archive name and your retained
root hash and private bucket name:

```sh
scripts/research-recovery exercise \
  --name private-season-recovery-001 \
  --database edgeeagle \
  --bucket YOUR_LOCAL_RESEARCH_BUCKET \
  --root YOUR_TRUSTED_ROOT_SHA256
```

`--database` defaults to `edgeeagle`. The command allows only local EdgeEagle
research/test database and bucket names. PostgreSQL and Floci connections use
`127.0.0.1`, explicit dummy local credentials, and the usual
`EDGEEAGLE_POSTGRES_PORT` / `EDGEEAGLE_FLOCI_PORT` overrides. It accepts no remote
destination. Docker must use a local Unix socket; the PostgreSQL system identifier
must match between Compose and the loopback connection before a dump or restore.
The pinned Compose PostgreSQL image supplies `pg_dump` and `pg_restore`; no
additional client installation or provider/AWS credentials are required.

Outputs live under ignored `.data/recovery/`:

- `<name>/`: owner-only archive with `database.dump`, `raw.bin`, `root.json`,
  numbered page files, canonical `inventory.json`, and final `COMPLETE` marker.
- `<name>-backup.json`: separately retained inventory hash, root, source audit and
  PostgreSQL tool/server identities; created before attempting the restore.
- `<name>-<unique-id>-verification.json`: timestamps, exact temporary resource
  names, verification results, cleanup flags, and source-preservation checks.
  Failures remain `incomplete` and the command exits nonzero.

Never overwrite an existing archive or backup report. A failed archive write may
leave an incomplete directory; keep it for inspection and choose a new name.
No public artifact upload is part of this command. Raw provider data, SQL dumps
and private reports must not enter Git or hosted CI.

## Verify an existing trusted backup

Read the inventory hash from the separately retained backup report, not from a
newly calculated hash of potentially changed files:

```sh
scripts/research-recovery verify \
  --name private-season-recovery-001 \
  --inventory-sha256 YOUR_RETAINED_INVENTORY_SHA256 \
  --trusted-local-backup
```

This mode requires no source bucket or source database. It validates the full
archive and replays all results **before** creating destination resources. The
restore uses new UUID-named databases/buckets, restores the dump in one transaction,
then raw data, pages, and root. Verification reads only those restored stores and
compares canonical receipt bytes against restored PostgreSQL. All consumer
connections close before database cleanup; S3 clients close after owned-object
cleanup. Temporary targets are removed on success and on handled failures.
Only targets confirmed created by the current exercise are eligible for cleanup.
An interrupted process, lost create acknowledgement, or cleanup error can leave
resources: inspect the recorded exact names, never delete by a broad prefix.

## Limits and interpretation

- Only use your own trusted operator-created dump. A checksum is not a SQL
  sandbox: restoring an arbitrary PostgreSQL dump can execute database code.
- Root is capped at 64 KiB; raw and each page at 1 MiB; at most eight pages;
  database dump at 64 MiB. Source object audits refuse buckets above 1,000 objects.
  Commands have a 60-second subprocess timeout; network calls and SQL statements
  also have explicit timeouts. Subprocess output is staged privately on disk,
  checked for size, then loaded into bounded memory.
- Files must be regular, owner-only, single-link files in an owner-only directory.
  Unknown names, symlinks, unexpected inventory bytes, corruption, missing members
  and incomplete markers fail closed. No directory is recursively archived.
- The dump snapshots PostgreSQL internally; it is **not** a distributed snapshot.
  The trusted immutable root selects the verified data. Source checks compare
  server/database identity, selected table counts, canonical receipts, schema
  version and bucket object listings before/after. They are not a full database
  audit or proof against a concurrent malicious writer. Run with local research
  writers stopped.
- All database schema/data is copied, but semantic verification covers only the
  selected root's receipts. Acquisition metadata and separate human approval
  files are not included by the initial command; keep the private acquisition
  directory and policy evidence separately.
- This is a same-machine recovery exercise, not protection against disk loss,
  off-device disaster recovery, encrypted archival storage, PITR, production
  execution, or an eligibility upgrade. Historical availability remains as
  retained; the private EPL capture remains replay-only, not backtest-eligible.

## Routine validation

Unit tests use synthetic bytes and mocked failures with networking blocked:

```sh
scripts/test-unit tests/unit/test_season_recovery.py tests/unit/test_recovery_archive.py \
  tests/unit/test_local_recovery.py tests/unit/test_recovery_cli.py
scripts/test-integration -k private_recovery
scripts/validate
```

The integration test uses authored results and disposable PostgreSQL/Floci
resources, not the private capture. It verifies dump/restore, matching receipts,
source preservation and cleanup. The explicit operator command is not run by CI.
