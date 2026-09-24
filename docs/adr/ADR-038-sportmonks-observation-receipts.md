# ADR-038 — Sportmonks observation receipts and atomic acceptance

**Status:** Accepted design direction; implementation deferred  
**Date:** 2026-09-24

## Context and scope

[ADR-037](ADR-037-sportmonks-fixture-adapter.md) implements retained single-fixture
parsing, explicit six-role mappings and canonical-linked staging from one pinned
reference snapshot. `NormalizedSportmonksFixture` is not a validated persistence
command; its frozen dataclass alone does not establish evidence integrity.

[ADR-018](ADR-018-event-acceptance-lineage.md) creates an event and its first
receipt together. Sportmonks instead references an **existing** event, potentially
created through another source. Reusing that operation would conflict with its
initial-only identity and overwrite/correction rules. Reuse the separation of raw,
reference and write transactions, not that receipt format or the Odds API codec.

## Decision: store observations, not authoritative event updates

Introduce a separate immutable Sportmonks observation receipt. One receipt covers
one validated single-fixture capture and its complete selected reference evidence.
Many captures and sources may describe one canonical event. Acceptance writes
only the new receipt; it does not insert/update events, participants, mappings,
results, markets, existing receipts or publication intents. It does not designate
a latest/authoritative source. Existing API responses remain unchanged.

The supported subset remains scheduled soccer with exact kickoff agreement and
the existing season/role checks. A changed kickoff/status, conflicting source, or
retargeted capture must not silently repair current state. Source arbitration,
rescheduling, cross-source supersession and other lifecycle states remain deferred.

## Receipt content and validation

Use a provider-specific format-1 envelope, independent of all existing receipt
format numbers. Retain:

- the full capture manifest, raw reference/checksum/size and all raw timestamps;
- actual versus simulated capture origin/clock and rights-evidence reference;
- parsed native fixture, league, season, sport, state and participant IDs, names,
  roles and UTC kickoff;
- selected source, canonical sport/competition/season/event, participants/entries;
- all six complete selected mapping revision values in sport/competition/season/
  home/away/event order, including decision provenance and the UTC mapping cutoff;
- explicit receipt, identity, parser and normalizer versions.

Usage is derived from origin, never freely selected. `available_at` stays unknown:
AUTHORED_FIXTURE is SYNTHETIC_ONLY; a reviewed actual capture is REPLAY_ONLY.
Rights hashes are references, not permission or authenticated evidence. This
contract adds no live acquisition or provider-rights approval.

The bounded codec must validate types, exact field coverage, versions, native
bounds, source/key/target agreement, role/hierarchy consistency, clocks, scheduled
state and kickoff/season agreement. Reject duplicate keys, unsupported tags,
nonfinite values, missing/extra fields, malformed/deep or oversized input. Use an
8 MiB receipt limit; raw bytes retain the independent 1 MiB limit. No payload can
select executable imports/classes. Canonical encoding uses sorted JSON keys,
compact separators, ASCII escaping, explicit nulls, UTC timestamps and exact
Decimal strings for mapping confidence. Sort event entries by participant ID;
retain mapping role order. Offset/display differences are not new evidence.

Structural receipt validation does not prove raw fidelity. Before acceptance,
re-read exact retained bytes, verify size/hash, parse under the pinned version,
and reproduce/compare the complete candidate using **retained** context. Do not
query current mappings during replay. Missing/corrupt raw, changed native fields,
inconsistent evidence or unsupported versions fail without writes. Replay proves
reproducibility, not authenticity, review authority or historical eligibility.

## Identity, retry and correction

Define capture identity as lowercase SHA-256 over a canonical object containing
identity version 1, the complete capture manifest and parser/normalizer versions.
Freeze its exact field representation with golden fixtures when implementing the
codec. Exclude canonical targets, mapping revisions/cutoff and derived native
output from identity. Receipt format alone is not a new observation identity.

An exact retained retry compares the **entire canonical receipt**, not only its
digest. Same identity with changed evidence/projection is a conflict, including a
fresh normalization that selects a later mapping revision or cutoff. A digest
collision fails closed. Never overwrite, relabel, or silently append a corrected
mapping result for the same identity.

Distinct acquisition manifests or explicitly supported transformation versions
can have distinct identities. They are separate observations, not automatic
corrections or supersession. Do not invent a new capture timestamp or bump a
version merely to evade a conflict. Correction of an already accepted observation
requires a later explicit linked correction/supersession contract; preserve the
original evidence until then.

## Storage and transaction contract

The ingestion-owned acceptance port will expose `accept(receipt)` returning 1
for a new receipt or 0 for an exact retained retry, and `get(capture_id)` returning
validated retained evidence or None. These are proposed internal interfaces, not
implemented commands or public APIs. Persistence depends inward on ingestion.

Add a separate `sportmonks_capture_receipts` table with capture ID primary key,
source and canonical event restrictive foreign keys, native fixture ID, receipt
format and complete canonical receipt bytes. Indexed columns must agree with the
decoded receipt. One fixture per receipt needs no duplicate child projection table.
Keep capture ID unique across all event targets so retargeting cannot bypass retry
conflicts. Immutable guards reject UPDATE/DELETE/TRUNCATE; they are accidental
mutation protection, not security against a database owner.

Use a caller-owned non-autocommit READ COMMITTED transaction and an operation
savepoint. Serialize same-identity attempts through the unique receipt insertion;
on conflict, compare the committed retained receipt in a subsequent statement.
Concurrent identical attempts converge to 1/0; differing receipts conflict, even
when targeting different events. Any validation/readback failure rolls back the
whole operation, including a tentative insert when the caller catches the error.
The repository never commits or retries automatically.

For a new identity, verify that selected immutable mapping revisions still exist
unchanged and that current canonical records equal the selected context. Do not
replace selected revisions with a later mapping decision. A later revocation does
not retroactively rewrite the earlier snapshot; accepting that snapshot records
evidence, not current suitability. Reject canonical drift between resolution and
first acceptance. Lock referenced canonical rows in a documented deterministic
table/ID order through validation/commit. Event-entry writers must honor the event
parent lock; arbitrary owner SQL outside that protocol is not made safe here.
The implementation must test lock ordering/concurrent drift and propagate bounded
lock/statement failures, leaving retries to the caller.

Exact existing retries and `get` validate stored bytes and indexed identity without
re-resolving current mappings or requiring current display/status values to match.
They neither refresh nor reapprove the observation. Missing/corrupt stored evidence
is an error, not a reason to recreate it from current references.

Raw verification and reference reads finish before the write transaction. S3 and
PostgreSQL are not one distributed transaction: rollback can leave reusable raw
bytes, and database commit cannot guarantee that an object will remain available.
The import coordinator must compare readback and report success only after commit.
Retained retry takes original evidence and verifies raw again before writing.

## Rollout, validation and limitations

Implement in independently committed increments:

1. Strict codec, deterministic identity and retained-context replay, with golden
   bytes and negative offline tests. Share deterministic validation with fresh
   normalization; do not create competing projection rules.
2. Additive schema and verified reader before enabling writers. Test migration
   round trips in disposable databases and preservation of all legacy receipts.
   Downgrade must lock/check and refuse while Sportmonks receipts exist, never
   delete/convert retained evidence. No automatic application-database migration.
3. Atomic acceptance: 1/0 retries, same-identity/different-target races, conflicts,
   current-context drift, retained retries after revocation, readback corruption,
   savepoint/outer rollback and no event/mapping/outbox changes.
4. Compose approved local file -> retained Floci raw -> pinned PostgreSQL reference
   snapshot -> normalization/receipt/replay -> atomic receipt acceptance/readback.
   Use authored data; prove deterministic replay after mapping/name changes.
5. Run `scripts/validate`; report local versus hosted/live evidence separately.

This ADR implements no codec, migration, reader, writer or import entry point.
No API/MCP/browser, dataset-catalog/recovery integration, historical Parquet,
model-ready dataset, outbox, live provider call or execution capability is added.
Those consumers need explicit later contracts; existing Football-Data recovery
coverage must not be represented as coverage of these future Sportmonks receipts.
