# ADR-031 — Read-only local retained-dataset catalog

**Status:** Accepted; pure read model implemented, local composition pending
**Date:** 2026-09-23

## Decision

Add a bounded private operator catalog for explicitly pinned ADR-029 season roots.
This is the first discover/inspect slice, not a production catalog, SQL registry,
automatic S3 scan, hosted API, web surface or modification of existing snapshots.
The owner-approved private dataset remains local and replay-only.

An operator-maintained, Git-ignored JSON configuration selects one local Floci
bucket and up to 32 unique trusted root hashes with display labels. Labels are
annotations, not verified sporting facts or mutable aliases for dataset identity.
Identity is always the full root hash. Configuration is at most 16 KiB and accepts
only `{format: 1, bucket: string, entries: [{root_hash: string, label: string}]}`.
Duplicate fields/roots, unknown fields, unsupported versions, malformed hashes,
blank/control-character labels or labels over 120 characters fail before storage
access. Empty catalogs are valid. Output ordering is by root hash.

Ingestion owns the typed read model and read-only orchestration. Persistence owns
the local file/Floci composition and JSON operator command. Existing immutable
raw/root/page adapters and complete-capture replay remain authoritative. No new
dependency, schema migration, store write, provider request or current mapping
lookup is needed. Missing/corrupt artifacts are errors, not automatic repairs.

## Listing and verification are different

`scripts/datasets --catalog PATH list` reads each selected root, checks its exact
hash and strict root codec, and emits retained source/capture provenance, parser
and normalizer pins, declared row/page counts and eligibility restrictions.
Listing reads no pages/raw payloads and always reports `NOT_CHECKED` replay state.
It fails as a whole if a selected root cannot be read; no successful prefix or
silent omission is returned.

`scripts/datasets --catalog PATH inspect ROOT_HASH` accepts only an explicitly
cataloged root. It verifies every page and the full original raw capture using
ADR-029 replay, then emits a freshly timestamped `VERIFIED` result with verified
receipt/participant counts, asserted kickoff range, canonical scope IDs and
retained context versions. No results are persisted as a durable verified flag.
The timestamp describes completion of this observation, not future retention,
historical availability, provider authenticity or acceptance in PostgreSQL.

Every result has `usage=REPLAY_ONLY` and `backtest_eligible=false`. Stable reason
codes identify the replay-only contract and unproven context availability; unknown
raw availability adds its own reason. Known raw timestamps never remove the first
two restrictions. Kickoff timestamps are retained assertions, not independently
verified clocks. Rights, canonical database acceptance, historical features/model
inputs and training eligibility are not established by this inspection.

## Local boundary and validation

The CLI uses only loopback Floci, explicit dummy credentials, disabled proxies and
bounded SDK timeouts/retries. It creates no bucket and accepts no remote endpoint.
Private configurations and captured output stay under `.data/`; never add real
provider data to fixtures or hosted CI. Errors go to stderr with nonzero exit and
no partial successful JSON. All client resources close on both success and failure.

Implement in dependency order: this ADR, pure read model/tests, then private CLI
composition with synthetic local integration coverage and real read-only inspection.
Test absent/changed roots/pages/raw, unlisted roots, ordering/bounds, no writes,
fresh verification semantics and unchanged eligibility. Run full validation before
handoff. API/UI exposure is a later additive consumer increment, not authorization
to host the private dataset or bypass authentication/licensing review.

`edgeeagle_ingestion.dataset_catalog` implements frozen catalog entries, metadata,
listing and inspection results. It reuses strict root decoding and complete replay;
no storage or database adapter is imported into ingestion. Offline tests cover
unknown and known raw availability, fresh status, missing artifacts, trusted-root
mismatch, bounds, deterministic ordering and write-free behavior.
