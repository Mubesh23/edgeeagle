# ADR-014 — PostgreSQL storage for provider mapping history

**Status:** Accepted for the internal Phase 2 schema and compare-and-append repository
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
  the repository locks before accepting a revision.
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

## Repository guarantees and limits

The repository locks the provider-key row, loads complete visible history, reuses
ADR-013 validation, and accepts the next revision in one caller-owned transaction.
It enforces nondecreasing inter-revision timestamps and revocation target retention;
these cross-row rules are not duplicated in the migration. Tests exercise exact
replay and conflicting concurrent writers, including first-key creation races.

Fixture ingestion now reads this repository through the pinned composition in
[ADR-025](ADR-025-mapping-backed-fixture-context.md). No mapping-write API or
automatic decision workflow is added. Direct SQL can still
create histories violating the repository's cross-row rules; repository reads,
appends, and replays reject those histories through the pure resolver.
Reads used for research need a pinned snapshot, not only an availability cutoff.
Reviewer names remain provenance, not proof of authorization.

## Repository append/replay contract

The internal repository accepts a complete `ProviderMappingRevision`. Its
`(key, revision)` is the stable replay identity and optimistic concurrency token.
Within a caller-owned READ COMMITTED transaction, create the key if absent, lock
its row, load and validate complete history, then compute the next revision as
`len(history) + 1`. Accept the proposed revision only if it equals that number.
There is no automatic renumbering or blind retry of a conflicting decision.

An already-stored revision is a successful replay only when every domain field
matches. Compare aware timestamps as UTC instants and Decimal confidence by value;
timezone labels and numeric display scale are not separate decision metadata.
A changed field or skipped/stale new revision raises an explicit conflict. A
later legitimate correction uses a new revision, even if its target repeats.
Validate the complete stored history before accepting a replay; malformed future
history must still fail closed. Preserve all original decision timestamps on retry.

Revision allocation is therefore compare-and-append under a row lock, not an
unconditional next-number API. Callers may propose the next number from a previous
read but must handle conflict explicitly. This needs no new replay table/column.
READ COMMITTED is required for writes so a waiter sees newly committed history
after acquiring the lock. Other isolation levels remain usable for reads, including
pinned REPEATABLE READ snapshots. The caller owns timeout, transaction retry, and
multi-key lock ordering; authentication/reviewer approval remains outside this port.

## Alternatives considered for replay

- Content hashes: rejected because equal-looking later decisions can be legitimate
  new revisions; content alone is not transport identity.
- Separate transport UUID: deferred until an ingestion request contract requires
  it; key/revision already identifies the immutable decision being redelivered.

## Storage alternatives

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
