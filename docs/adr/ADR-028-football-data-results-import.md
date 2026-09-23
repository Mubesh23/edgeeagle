# ADR-028 — Retained Football-Data CSV results imports

**Status:** Accepted; bounded local workflow implemented with synthetic-fixture validation  
**Date:** 2026-09-23

Receipt rollout status: `SoccerResultEvidence`, format-3 codec and migration
`0010_soccer_receipts` are implemented. CSV normalization and retained-receipt
replay, snapshot-kind dispatch, and end-to-end composition are implemented.
Legacy byte/digest golden tests and local PostgreSQL rollout/
downgrade guards cover the additive reader/schema increment.

## Context and Phase 2 gate

The fixture raw-to-canonical-to-event-to-API exit is demonstrated locally. Stored
manifest retrieval now composes with replay after reference edits and raw loss.
This permits the first Phase 3 offline adapter; it does not close the known Floci
delivery-DLQ gap or claim hosted-worker, authorization, catalog, or historical
research readiness. Those capabilities are not prerequisites for this bounded,
caller-controlled offline import.

The provider's field notes describe CSV results but do not supply native match IDs,
per-row availability evidence, or a kickoff timezone in that field definition.
Existing canonical events require an aware start instant. Never invent midnight,
assume UTC, or infer historical availability from a completed result. Provider
schema observations and sources belong in [the provider matrix](../data/provider-evaluation.md).

## Initial supported subset

- Local CSV only; reuse bounded `LocalFileImporter` and `ingest_raw` before parsing.
  No downloader, paid call, HTTP mock, or provider credentials are needed.
- UTF-8 (optional BOM), comma-separated header with unique nonempty column names.
  Require `Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR`. Extra named columns are
  retained in raw bytes but not normalized. Do not claim odds/statistics support.
- Date is exactly `dd/mm/yyyy`, time exactly `HH:MM`, result H/D/A, goals unsigned
  base-10 integers 0..99 consistent with result. Older two-digit years, absent
  kickoff times, unfinished results, blank/duplicate/irregular rows, and malformed
  CSV fail explicitly. No silent row dropping, coercion, or partial acceptance.
- Limit a capture to 1 MiB and 100 rows initially. Snapshot envelopes retain their
  existing 1 MiB bound; reject oversized snapshots, never truncate. This is a
  bounded results batch, not whole-archive/whole-season coverage. Partitioning is
  separate future work; no claim that every provider file fits.

## Identity and canonical normalization

Use an adapter-owned versioned row locator, not a fabricated provider-native ID:
`football-data-row-v1:<sha256>`, hashing canonical compact ASCII JSON of the ordered
array `[resource, division, ISO match date, home label, away label]`. Source ID scopes
the enclosing `ProviderEntityKey(type="event")`. Row position and kickoff clock
are not identity. Reject duplicate locators and canonical event-ID collapse.
Date/team corrections require explicit reconciliation rather than automatic merging.
Source identity is caller-supplied: real files use the registered Football-Data
source; authored test data uses a distinct synthetic source. No Venue is inferred.

Each row requires an explicit internal event ID, context version, exact division
and team label guards, the five source-scoped reference keys, and a signed integer
UTC offset in minutes (-840..840). The offset is asserted per row by the caller,
not inferred from division/country/server timezone; its correctness/retention rights
are caller prerequisites. This avoids timezone-database drift in replay. Missing
or uncertain offsets block the import; supplying one is not historical evidence.

Resolve the batch's canonical references and mapping revisions through the existing
pinned REPEATABLE READ read-only reference port, after raw I/O. Require canonical
sport code `soccer`, TEAM participants, valid season/event hierarchy, and complete
one-to-one row/request coverage. Reuse the existing mapping-evidence shape and
exact labels; its current `FixtureMappingEvidence` name does not make CSV native
IDs exist or assert a real provider capture. Do not introduce fuzzy resolution,
mapping writes, or automatic canonical ID generation.

Project event status `FINISHED`, aware UTC kickoff, and HOME/AWAY entries. Preserve
canonical `SoccerResultEvidence(home_goals, away_goals, utc_offset_minutes)` on the
candidate. It is a recorded full-time score and import context, not a settlement,
risk, payout, or pricing decision. Provider CSV headings/results codes stop at the
adapter. Parser version `football-data-results-csv-v1`; normalizer version
`football-data-results-mappings-v1`. Unknown capture times stay null; kickoff is
not result publication time.

## Additive receipts and replay

Add optional `soccer_result` to EventCandidate. When absent, omit it entirely from
serialization and lineage identity, preserving every format-1/2 byte and digest.
When present, require mapping evidence, supported soccer/TEAM context and FINISHED
status; format 3 includes the canonical score and asserted offset. Include it in
lineage identity. Strict readers round-trip/revalidate all evidence. An additive
migration permits format 3 without rewriting rows, and refuses downgrade while
format-3 data exists. Deploy readers/schema before enabling writes.

Use the existing initial-only event acceptance repository: exact replay is a no-op;
changed raw/context/results or conflicting event IDs fail, never update silently.
Accept the complete validated batch inside one caller-owned transaction. S3 raw
retention precedes it; manifest storage follows commit, so failure can leave orphan
raw artifacts or committed receipts without a manifest. Retry from retained input
and receipts; there is no cross-service transaction or automatic repair.

Extend internal manifest format 1 with a distinct `FOOTBALL_DATA_RESULTS_REPLAY`
kind. It contains only nonempty complete CSV captures with supported format-3
receipts; mixed synthetic/CSV captures fail. Existing `MAPPED_EVENT_REPLAY` bytes,
goldens, empty-capture support, storage layout and dataset-version hashing remain
unchanged. The codec chooses the kind from validated candidate versions/evidence;
strict decode must match that kind. New readers accept both; old readers reject
unknown kinds safely. No public API/event schema changes.

Replay dispatches by validated kind and calls the corresponding deterministic
normalizer using retained mapping context and per-row offsets, never current
tables. Verify complete coverage, exact raw hash/size, versions, full candidate
equality, score consistency, and requested dataset version. Storage and verification
remain separate; no successful prefix is returned. All kinds remain `REPLAY_ONLY`.
This is not Parquet, a model-ready dataset, or approval for backtesting/settlement.

## Validation and delivery

1. This contract, provider schema notes, and roadmap scope.
2. Receipt value/codec/migration compatibility before CSV writes, with legacy
   golden tests and disposable PostgreSQL upgrade/downgrade guards.
3. CSV parser, pinned normalization and replay, with authored fixtures, offline
   malformed/duplicate/time/identity tests and retained snapshot support.
4. Local composition: retain a file, normalize, accept atomically, build from
   accepted receipts, store/retrieve manifest, replay without current reads.
   Cover exact repeated imports, batch rollback, later reference edits, malformed
   inputs retained without canonical writes, raw loss, and missing manifests.

No downloaded provider dataset is committed or acquired for these tests. Authored
synthetic fixtures establish behavior against the documented subset, not live
provider compatibility or licensing permission. Caller-supplied real files require
separate rights review before acquisition/use. No new licensing assumption, IAM,
production resource, risk behavior, dependency, or API is introduced. Use the
existing root checks and full `scripts/validate` before handoff.

The `edgeeagle_ingestion.football_data` adapter now exposes `FootballDataRequest`,
`row_locator`, `normalize_results`, and `replay_results`. It validates the whole
CSV and request coverage before a single pinned reference snapshot; canonical
construction additionally rejects kickoff outside the supplied season. Replay uses
the same parser/projection with retained evidence. Network-disabled tests cover
malformed CSV, source/label/identity conflicts, bounds, offsets, mapping/snapshot
failures, and full-output drift. Run `scripts/test-unit tests/unit/test_football_data.py`.
`tests/unit/test_football_data_manifest.py` covers CSV snapshot round trips, kind
dispatch, mixed/empty-group rejection and score drift. Existing synthetic manifest
goldens and storage tests remain unchanged and pass with the additive reader.

`football_data_import.import_results_dataset` now composes acquisition, pinned
normalization, complete-batch transactional acceptance and receipt reads, then
manifest storage after commit. It validates manifest size before commit, orders
event locks by ID, and rejects a mismatched storage acknowledgement. It creates
no outbox notifications. Caller-supplied transaction contexts own commit/rollback,
connection lifecycle and timeouts; no application database is migrated automatically.
Run `scripts/test-integration -k football_data_import` for disposable PostgreSQL/
Floci evidence: exact/concurrent retries, final-row conflict rollback, malformed
raw retention without canonical writes, post-commit manifest failure recovery,
reference revocation/edits, and missing/corrupt raw artifacts. See the
[local workflow guide](../development/football-data-import.md).
