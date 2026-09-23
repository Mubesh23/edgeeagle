# ADR-025 — Mapping-backed fixture reference context

**Status:** Accepted for incremental Phase 2 implementation; persistence pending  
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
and the dual-format codec are implemented; the migration, pinned PostgreSQL
composition, and mapped normalization remain pending.

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

Network-disabled tests cover cutoff boundaries, corrections/revocations, malformed
future histories, typed references, duplicate/source-mismatched keys, missing or
inconsistent records, deterministic results, and propagated repository failures.
Later increments must prove byte/digest compatibility and migration behavior with
disposable PostgreSQL databases before enabling mapped receipt writes. Full root
validation remains the handoff gate; no paid providers or AWS credentials.
