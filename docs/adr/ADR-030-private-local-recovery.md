# ADR-030 — Private local research recovery

**Status:** Accepted; portable archive implemented, local restore pending
**Date:** 2026-09-23

## Context

The first private EPL results capture now has 380 canonical receipts and a
verified ADR-029 replay root. PostgreSQL and Floci named volumes retain it, but
neither conditional object writes nor local volume persistence is a backup.
The owner requested a complete local backup-and-restore exercise without touching
live research data. No cloud copy, commercial rights or production recovery
guarantee is authorized.

## Decision

Add explicit local operator tooling, separate from domain/provider logic and
routine provider acquisition. Preserve the ADR-029 wire codecs and trusted root.
No current mapping resolution, renormalization or provider fetch may substitute
for missing evidence during recovery.

The recovery set contains:

- A PostgreSQL custom-format logical dump of the selected local research database,
  including schema, canonical records, mapping history and immutable receipts.
- The canonical root and every hash-pinned page, plus the exact raw capture body.
  The root already pins full raw capture metadata; restore through the existing
  raw adapter to reproduce its identity and metadata.
- Optional explicit local evidence files such as original acquisition metadata,
  reviewed bindings and approval/verification reports. Never recursively copy a
  workspace, environment file, credentials or arbitrary operator code.
- A versioned inventory with byte sizes and SHA-256 hashes, the trusted replay
  root and a completion marker written only after all backup checks succeed.

Backup artifacts stay in a new Git-ignored private local directory, outside the
live service volumes, with owner-only permissions. Never overwrite an existing
backup. Incomplete output remains visibly incomplete; no success inventory is
published after a failed step. Fixed file names/bounds and integrity checks must
reject path traversal, symlinks, unexpected members and truncated/corrupt content.
Retain the inventory hash separately in the operator report: hashes detect
accidental change, not malicious forgery or provider authenticity.

The PostgreSQL dump is transactionally consistent internally, not a distributed
snapshot across services. The selected immutable root identifies the dataset
being protected. Before declaring restoration successful, require all replayed
receipts to equal PostgreSQL readback under canonical receipt encoding. A mismatch
or absent object fails the whole verification. Other database state is copied by
the dump but is outside the selected dataset's semantic verification.

## Restore safety and evidence

Restore only a trusted operator-created backup, never an arbitrary downloaded
SQL archive. PostgreSQL restores can execute database code; a checksum is not a
safe SQL sandbox. Tooling must accept no remote database/S3 destination and no
option to overwrite the developer database or source bucket.

Create fresh uniquely named recovery database and bucket resources. Refuse
collisions rather than clean or reuse existing targets. Never run restore with
`--clean` against live state. Only resources successfully created by the current
exercise may be cleaned up, after all clients are closed; failure must not widen
the cleanup target. Keep the backup and verification report regardless.

Validate all inventory members and replay completeness before destination writes.
Restore the trusted dump, raw capture, pages, then root. Verify the restored root,
all results and canonical receipts without contacting original artifact stores
or resolving current mappings. Check live source identity/counts before and after
the exercise. Record exact targets, trusted hashes, versions and results.

Routine tests use authored synthetic data and disposable local resources. Real
files/exports never enter Git or hosted CI. The actual 380-row exercise is explicit
and local. No backtest eligibility, historical availability, production IAM,
Object Lock, point-in-time recovery, off-device disaster recovery or encryption
guarantee is added.

## Delivery increments

1. This decision and recovery acceptance criteria.
2. Bounded portable replay artifact export/import with strict local inventory and
   corruption/failure tests, preserving root identity.
3. Local PostgreSQL snapshot/isolated restore composition and synthetic end-to-end
   tests; stable documented operator commands with fail-closed target checks.
4. Private real-data backup and isolated restoration proving all 380 receipts and
   results, source preservation, cleanup of only exercise-owned resources, and
   full repository validation.

Backup durability against disk loss requires a separately approved destination
and storage/security policy. This decision does not silently introduce one.

## Implementation status

`edgeeagle_ingestion.season_recovery` exports, verifies and restores a bounded
in-memory set (`root.json`, numbered pages and `raw.bin`). It reuses ADR-029
complete-capture replay, rejects missing/extra/corrupt members before writes,
preserves raw metadata, checks storage acknowledgements and publishes the root
last. This layer has no filesystem, database or provider access.

`edgeeagle_persistence.recovery_archive` adds exclusive owner-only directory/file
creation, a canonical inventory and final completion marker. Loading requires a
separately retained inventory hash; it rejects symlink/nonregular/hardlinked or
nonprivate members, unknown names, changed content and incomplete archives before
replay. The initial PostgreSQL dump limit is 64 MiB; root, raw and page limits
remain bounded by ADR-029. It loads validated bytes into bounded memory before
restore to avoid reopening mutable archive files during destination writes.
PostgreSQL recovery composition is the next increment.
