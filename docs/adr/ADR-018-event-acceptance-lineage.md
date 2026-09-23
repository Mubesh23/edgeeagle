# ADR-018 — Transactional initial event acceptance and lineage

**Status:** Accepted for Phase 2 fixture ingestion  
**Date:** 2026-09-22

## Decision

The ingestion application owns an `EventAcceptanceRepository` port over validated
`EventCandidate` values. Persistence may depend inward on ingestion (which depends
only on domain); ingestion never imports persistence. No API dependency is added.

`accept(candidate)` inserts an event, its participant entries, and one immutable
normalization receipt atomically inside a caller-owned PostgreSQL transaction.
It returns True for a first acceptance and False for an exact replay. The canonical
event ID is one replay identity for this **initial-insert-only** operation. Changed
event/entry data, provenance, or any version conflicts rather than overwriting.
An event inserted outside this operation without a receipt also conflicts.
This is not the future multi-source refresh/correction/versioning policy.
A second unique identity is the SHA-256 of canonical JSON containing the raw
reference, provider event key, and parser/normalizer/context versions (not output
event IDs or entries). Thus one lineage cannot produce two canonical event IDs.
A digest collision fails closed as a conflict; replay still compares the full
snapshot. JSON keys are sorted, with compact separators and ASCII escaping.

Use READ COMMITTED for writes. The existing event primary-key constraint serializes
competing initial inserts. On duplicate insertion, roll back that insert savepoint,
lock the existing event row, then compare the stored receipt and current event and
entries. Identical concurrent writers converge; different writers conflict.
Direct SQL writers changing child rows without the parent lock are outside this
initial-insertion protocol; a future update path must define its locking policy.
The operation has its own encompassing savepoint so a receipt failure cannot leave
an event or entries behind when a caller catches the error. It does not commit.
Callers own timeouts, retries, and consistent multi-event ordering. Reference
entities must already exist; they are neither created nor updated implicitly.

Migration `0005_event_acceptance` adds `event_normalizations`: event ID primary key
and restrictive FK, source ID restrictive FK/index, unique lineage digest
`acceptance_key`, and a versioned JSONB snapshot.
The snapshot preserves the complete accepted event/entry projection, raw reference
(capture timestamps, checksum, length), provider event key, and parser/normalizer/
context versions. Schema checks tie snapshot identities to indexed FK columns.
An immutable trigger rejects UPDATE/DELETE/TRUNCATE. This is not tamper resistance
against an owner disabling triggers. Downgrade removes only the new table/function.

Snapshot format 1 uses explicit dataclass field names and typed-ID value objects,
UTC ISO timestamps, and participant-ID-sorted entries. Entry order and timestamp
display offsets do not affect replay equality. Readers reconstruct and validate
records and reject malformed, unknown-version, or noncanonical snapshots.
`get(event_id)` returns the accepted snapshot, not mutable current-state data.

## Limits

This transaction does not span S3. Callers retain/verify raw data first; the database
stores its reference but cannot prove that the S3 object still exists. Raw payloads
remain reusable after rollback. No reference supplies storage credentials/bucket
selection; those remain deployment configuration.

The receipt preserves accepted output and lineage references, not the full fixture
binding or canonical reference-data history. Callers must still retain the immutable
context identified by `context_version` (ADR-017). Historical datasets, production
mapping decisions, correction policy, context catalog, and backtest eligibility
are not implemented by this receipt. Unknown availability remains unknown.

No outbox/event publication is added yet. Before downstream consumers rely on this
operation, durable publication must be committed in the same database transaction.
After that come local EventBridge/SQS/DLQ tests and a read-only API path; these
complete the Phase 2 fixture pipeline before Phase 3 real-provider adapters.

## Validation

Offline migration SQL, disposable PostgreSQL migration round trips, receipt
constraints/immutability, exact/conflicting concurrent replays, commit visibility,
rollback, and Floci fixture-to-canonical persistence. No application database reset,
production deployment, credentials, or paid provider calls.
