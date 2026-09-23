# ADR-029 — Bounded whole-season CSV replay

**Status:** Accepted for incremental implementation; implementation pending  
**Date:** 2026-09-23

## Context

The owner approved private research with no commercial deployment of the downloaded
Premier League 2024/25 results file. See the separate rights and time evidence in
[provider evaluation](../data/provider-evaluation.md). This decision grants no
additional licensing permission and does not infer historical availability.

ADR-028 accepts at most 100 rows and ADR-026 limits a complete manifest to 1 MiB.
The requested file contains 380 rows. One existing synthetic format-3 receipt is
4,066 bytes; 380 equivalent receipts alone occupy 1,545,080 bytes before pins or
envelope overhead. This is a sizing example, not a measurement of real receipts.
Increasing the row limit alone cannot meet the complete-season requirement.

## Decision

Retain the original CSV unchanged as one provider capture. Never cut it into
derived files and label those as original provider captures. Add a separate,
bounded whole-season normalization/replay profile and a paged receipt bundle.
Leave the original 100-row profile, manifest codec, storage keys and byte limits
unchanged. There is no rewrite of previously accepted receipts or manifests.

### Normalization profile

- New parser pin: `football-data-results-season-csv-v1`.
- Keep `football-data-results-mappings-v1` and existing row-locator semantics:
  field interpretation and identity do not change, only the supported batch size.
- A complete capture is nonempty, at most 512 rows and at most 1 MiB of raw bytes.
  The 512-row bound accommodates the target's 380 rows with a fixed maximum of
  eight 64-receipt pages, not arbitrary archives or every league format.
- Validate all CSV rows, request coverage and identity uniqueness before resolving
  references. Resolve every row in one pinned read-only reference snapshot.
- Caller-supplied canonical event IDs, reviewed mappings, timezone offsets and
  context version remain mandatory. No team matching or timezone inference is
  introduced in the provider adapter. Scores stay in format-3 receipts.
- Whole-season replay accepts only the new parser pin and requires complete raw
  coverage. The original replay path rejects it, and vice versa. No pin relabeling.

### Receipt pages and root index

The implementation must define a strict, versioned root/page wire codec before
storage is added. Each object is canonical JSON with a content SHA-256 identity.
Both kinds are replay-only and are distinct from complete ADR-026 manifests.
Pages must never be accepted as independently verified complete captures.

The root pins one full raw reference, the new parser/normalizer pair, total row
count and an ordered list of page content hashes. It is at most 64 KiB. There are
one to eight pages. Each page is at most 1 MiB and contains at most 64 full receipts,
pinning existing acceptance keys and full canonical receipt hashes. Stable
provider-row-locator ordering determines page membership; all pages except the
last contain 64 receipts. No configurable chunk size or mutable latest pointer.

Each receipt must match the root capture and supported versions. Require unique
provider keys, canonical event IDs and acceptance keys across the entire bundle.
Reject duplicate pages, noncanonical ordering/encoding, unknown fields/versions,
invalid sizes and mismatched hashes. Root/page limits apply before JSON parsing.
An oversized receipt/page fails; never truncate or silently omit a row.

Read-only verification retrieves all hash-pinned pages through an inward-owned
storage port, validates the entire bundle, reads the exact original raw capture,
then calls the whole-season replay profile. Return only the complete eager result
in raw row order. Missing/corrupt pages or raw data fail, with no successful prefix,
provider fetch, current-state reconstruction or write. Retained offsets and
reference values are authoritative for replay, not today's timezone database.

### Acceptance and storage composition

Ingestion owns values, strict codecs, orchestration and the storage port;
persistence owns S3 adapters. Use a separate content-addressed namespace for root
and page objects, conditional writes, bounded reads and integrity-checked retries.
Do not change the existing manifest store's meaning or maximum object size.

Retain raw bytes, normalize the complete capture, then accept/read back every
candidate in one caller-owned PostgreSQL transaction using stable event-ID lock
ordering. Build and size-check every page/root from accepted receipts before
commit. After commit, store pages first and the root last. A root is the completion
reference, not proof that future artifact reads will succeed. No S3 I/O spans the
acceptance transaction, and no distributed atomicity is claimed.

Raw or page orphans and committed receipts without a root are possible. Exact
retry or explicit reconstruction from immutable accepted receipts can finish
storage. Never repair by rereading current mappings or replacing trusted pins.
No notifications, catalog, API, production resources, migration or dependency are
needed for this bounded operation. Existing acceptance conflicts remain errors.

## Alternatives rejected

- Raising the old manifest cap: changes its reader/storage contract and does not
  follow its documented partitioning boundary.
- Splitting provider CSV bytes into independently ingested files: loses the
  original-capture identity unless a new derivation contract is introduced.
- Committing each page independently: permits partial canonical seasons.
- Compressing an unbounded manifest: hides decoded-memory limits and does not
  establish completeness or immutable partition identity.

## Delivery and evidence

1. This decision, sizing evidence and implementation status.
2. New bounded parser profile and retained replay, with legacy compatibility,
   380/512-row success, 513-row failure, final-row errors, mixed-pin rejection and
   missing/changed raw tests. Synthetic rows only in routine tests.
3. Root/page codecs and complete verification, then conditional S3 storage.
   Test reordered inputs, page boundaries, duplicate/missing/final-page failures,
   corrupt hashes, unsupported versions, size limits and stream cleanup.
4. Whole-batch composition: exact/concurrent retries, final-row rollback,
   post-commit storage failure recovery, retrieved-root replay after reference
   edits, and no outbox writes. Run full root validation before handoff.
5. A separate explicit local real-data run after timezone evidence/mappings are
   reviewed. Retain capture metadata, exact canonical bindings, receipts, root
   hash and validation report locally. Prove all 380 results, retry idempotency and
   replay without current reference reads. No real CSV or result exports in Git.

Unknown availability remains null. Successful replay does not authorize historical
features, model training, backtesting, odds processing, settlement or execution.
