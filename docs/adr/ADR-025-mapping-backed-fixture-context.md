# ADR-025 — Mapping-backed fixture reference context

**Status:** Accepted and implemented for the local synthetic fixture path  
**Date:** 2026-09-23

## Context

ADR-014 mapping targets must already exist. Resolving an event mapping before
ADR-018 initial event creation would create a dependency cycle. The authored
fixture also lacks participant IDs, a season ID, and status (ADR-017). Neither
labels nor mapping confidence can supply those missing facts.

## Decision

Resolve only preexisting sport, competition, season, and home/away participant
references in this increment. Supply five explicit source-scoped provider keys
from a retained fixture manifest. Synthetic participant/season keys are authored
test identities, not claims about identifiers present in a real provider payload.
All five keys must belong to the same source and be distinct. Provider entity-type
names remain adapter-owned opaque namespaces; typed canonical targets determine
whether a mapping is appropriate for a role.

The ingestion resolver depends on domain repository ports, never persistence.
Validate complete per-key histories, including future revisions, using ADR-013.
Select the latest revision available at an explicit aware cutoff; reject absent,
revoked, not-yet-available, wrong-type, missing-target, or inconsistent references.
Never choose by confidence, infer identity from labels, or append mapping decisions.
Return immutable canonical reference records together with the selected revisions
in explicit sport/competition/season/home/away order and the UTC cutoff.

Callers must read mappings and canonical records from the same pinned snapshot
(REPEATABLE READ, read-only for PostgreSQL). A cutoff alone is insufficient.
The port-level resolver cannot inspect transaction isolation; concrete composition
must enforce it before this becomes an ingestion entry point. The returned records
capture current reference values, not a historical dataset or proof of availability.

The manifest continues to provide the new canonical event ID, exact label guards,
status, and context version. No event is preinserted to satisfy a mapping FK.
Automatic event matching, event-ID allocation, review authorization, and subsequent
event mapping registration are outside this decision.

## Receipt compatibility and rollout

1. Add the reference resolver and failure-path unit tests. This is a prerequisite,
   not wiring to persisted normalization. Do not discard its revision evidence to
   pass a mapping-derived binding through the legacy persistence path.
2. Introduce an additive format-2 receipt and a new migration permitting both
   formats. Retain role-specific provider keys/revision numbers, cutoff, selected
   canonical context, and explicit fixture context with mapped candidates.
   Validate evidence against candidate references and source. Preserve the old
   format-1 codec and acceptance digest exactly for legacy candidates. Include
   mapping evidence in the new lineage digest; changed evidence is not an exact
   replay, even if the projected event is unchanged. Existing receipts are never
   rewritten or silently upgraded. A downgrade must refuse when format-2 rows
   exist rather than deleting them. Reader rollout precedes format-2 writes.
3. Compose mapping-backed fixture normalization with pinned PostgreSQL reads and
   retained raw bytes. Acceptance remains a separate READ COMMITTED transaction
   with the existing initial-insert/conflict rules. Test immutable evidence after
   mapping corrections, exact replay, rollback, and fixture-to-API delivery.

No API/event-envelope change, production provider claim, timestamp inference,
new deployable, external call, or production permission change is authorized here.
Unknown raw availability stays unknown. Historical snapshots, unattended worker
readiness, and the Floci delivery-DLQ gap remain separate work.

## Validation

Implementation status: the port-level reference resolver and offline tests are
implemented in `edgeeagle_ingestion.fixture_references`. Format-2 candidate evidence
and the dual-format codec are implemented. Migration `0009_mapped_receipts` permits
both formats without rewriting receipts. The ingestion-owned mapped fixture
normalizer now verifies raw bytes/manifest coverage before resolving the complete
batch through one `FixtureReferenceReads` context. It closes the snapshot before
returning candidates with evidence and version `synthetic-event-mappings-v1`.
The legacy parser and normalizer versions remain unchanged. The persistence-owned
`fixture_reference_reads(engine)` factory now opens a fresh REPEATABLE READ,
read-only transaction per batch, with 5-second SQL and idle-in-transaction timeouts.
The caller owns engine lifecycle and connection/pool timeouts. The concrete resolver
checks active transaction, isolation, and read-only mode on each call; both
repositories use the same connection. Exceptions propagate and connections close.
Raw storage I/O precedes this transaction; acceptance remains a later, separate
READ COMMITTED operation. No transaction spans S3, broker delivery, or API requests.

`scripts/test-integration -k fixture_raw_to_api` exercises both legacy bindings
and mapping-backed manifests through retained S3 bytes, acceptance/outbox, actual
EventBridge/SQS duplicate delivery, consumer verification, and API reads. Additional
tests prove that concurrent mapping/reference edits do not change an open snapshot,
fresh snapshots see corrections, revoked mappings fail closed, and accepted
evidence survives later revisions. Retain the accepted candidate for exact retry;
a newly opened snapshot is not a frozen historical dataset, even at the same cutoff.

Format 2 adds `candidate.mapping_evidence`: exact competition/home/away guards and
the resolved references (canonical records, cutoff, and complete selected revision
values in sport/competition/season/home/away order). Event ID, status, source event
key, and context version remain on the candidate. Confidence uses canonical decimal
strings without rounding; timestamps serialize in UTC and status as its enum value.
Candidates without evidence omit the field entirely and retain format 1, including
its original lineage digest. Readers reject mismatched evidence or noncanonical
JSON. These constructors verify internal consistency, not that supplied evidence
was actually read from the mapping repository; pinned composition remains required.
Codec support must be deployed before format-2 writes are enabled.
The database check retains the original indexed identity checks and requires an
evidence object for format 2; full evidence validation belongs to the codec.
Evidence is a captured value, not a new foreign key or authenticated review record.
Downgrade takes an exclusive table lock before checking for format-2 rows, refusing
if any exist; it never deletes or converts them. No developer database is migrated
automatically. Legacy-row preservation and mapped replay/rollback are covered by
disposable PostgreSQL tests.

Network-disabled tests cover cutoff boundaries, corrections/revocations, malformed
future histories, typed references, duplicate/source-mismatched keys, missing or
inconsistent records, deterministic results, and propagated repository failures.
Byte/digest compatibility and migration behavior are tested with
disposable PostgreSQL databases. Full root
validation remains the handoff gate; no paid providers or AWS credentials.
