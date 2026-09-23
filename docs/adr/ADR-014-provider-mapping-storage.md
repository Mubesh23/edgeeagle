# ADR-014 — PostgreSQL storage for provider mapping history

**Status:** Accepted for the internal Phase 2 schema; repository workflow pending
**Date:** 2026-09-22

## Context

[ADR-013](ADR-013-provider-mapping-revisions.md) defines immutable mapping decisions
and a pure history resolver, but deliberately leaves physical persistence open.
Canonical source and target tables now exist. An untyped target string would not
let PostgreSQL enforce existence in the correct canonical namespace.

## Decision

- Add `provider_mapping_keys`, keyed by source ID, provider entity type, and
  provider entity ID. Preserve opaque case-sensitive strings with C collation.
  Store an immutable target kind on this key; it also supplies a per-key row that
  a future repository can lock before allocating a revision.
- Add `provider_mapping_revisions`, keyed by the provider key plus a positive
  bigint revision. Store the ADR-013 decision provenance, timestamps, status, and
  optional arbitrary-scale numeric confidence. PostgreSQL's numeric/bigint limits
  apply; values must never be silently rounded to a fixed application scale.
- Use six nullable typed target columns with restrictive foreign keys to sport,
  competition, season, participant, event, and venue. Exactly one must be populated
  and agree with the key's target kind. A composite FK fixes the type for the whole
  history. Multiple provider keys may reference the same canonical record.
- A generated predecessor revision and self-FK require every revision after 1 to
  reference the previous revision of the same key. Revision 1 must be MAPPED.
  This enforces contiguous committed histories without a mutable counter.
- Per-row checks enforce finite timestamps ordered validated <= available <=
  ingested, known status, nonblank provenance, and confidence in [0, 1].
- Reject UPDATE, DELETE, and TRUNCATE of both new tables using statement triggers.
  Corrections and revocations append decisions, not edits. These are accidental
  mutation guards, not security against a database owner who can drop/disable
  triggers. No roles, grants, reviewer authentication, or production IAM changes
  are introduced. Populated destructive migrations still require human review.

## Repository follow-up and limits

The schema increment is not a complete mapping persistence workflow. The next
repository increment must lock the provider-key row, load the complete history,
reuse ADR-013 validation, allocate the next revision, and append in one caller-owned
transaction. It must enforce nondecreasing inter-revision timestamps and revocation
target retention; these cross-row rules are not duplicated in this migration.
It must distinguish exact transport replays from conflicting writes, with a stable
replay identity and field comparison, and test concurrent writers. No schema-only
claim of replay handling or safe concurrent allocation is made.

Until that repository exists, no ingestion path or API writes these tables.
Direct SQL can still create histories violating the deferred cross-row rules;
the pure resolver rejects such histories rather than returning a mapping.
Reads used for research need a pinned snapshot, not only an availability cutoff.
Reviewer names remain provenance, not proof of authorization.

## Alternatives

- Generic `(kind, id)` target: rejected because it cannot enforce canonical FKs.
- Separate history tables per target kind: deferred to avoid six copies of the
  revision/provenance workflow; sparse typed columns cover the six current targets.
- JSON history blobs: rejected because references and revision uniqueness become
  harder to enforce and query.
- Duplicating the complete domain history validator in SQL triggers: deferred;
  the repository will reuse the deterministic domain implementation under a lock.

## Validation and rollout

Ship the ADR before its migration. Test offline SQL and upgrade/downgrade/reapply
in disposable local PostgreSQL databases, typed references, immutable writes,
predecessor integrity, timestamp/decimal guards, and preservation of prior tables.
No developer database migration or production deployment is automatic. The new
revision's explicit downgrade removes only its two tables and trigger function.
