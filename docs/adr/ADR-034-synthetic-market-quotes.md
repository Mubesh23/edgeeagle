# ADR-034 — Retained synthetic market and quote ingestion

**Status:** Accepted for implementation; executable support pending  
**Date:** 2026-09-23

## Goal and scope

Ingest an authored soccer market fixture, retain its provenance, normalize its
selections and quotes, persist them idempotently, and expose read-only API results.
This fills the market portion of Phase 2 before live Phase 3 provider adapters.
Reuse the authored odds fixture and bounded local-file/raw S3 path. This is a
synthetic adapter, not certification of The Odds API compatibility. The source
is explicitly synthetic; bookmaker keys resolve to separately supplied Venues.
No paid calls, private captures, production resources, new deployment, model,
fair price, EV, execution or historical eligibility are introduced.

## Canonical values and identity

Domain owns frozen Market, Selection and Quote values and typed identities.
Initially support only `RESULT_3WAY`, period `REGULATION_TIME`: soccer full time
including stoppage time, excluding extra time and penalties. Exactly HOME, DRAW,
AWAY selections; HOME/AWAY reference the corresponding event participants, DRAW
has no participant. No line or market-level participant. Unsupported semantics
fail explicitly. Do not scaffold totals, exchanges or additional sports.

Market ID derives from versioned canonical event ID/type/period semantics, never
source, venue, label or price. Selection ID adds the canonical outcome. Use SHA-256
of compact sorted-key ASCII JSON with an explicit identity version and golden
vectors. Compare full semantics on replay; a hash is not authentication.

Quotes are immutable observations, not executable/current prices. Require finite
Decimal odds greater than one; reject booleans and binary floats at the domain
boundary. Parse JSON numbers directly into Decimal and preserve exact values in
PostgreSQL numeric and decimal-string API fields without rounding.
Keep source, venue, selection, optional provider quote ID and effective/observed/
available/ingested timestamps distinct. Ingestion is required; unknown other times
remain null. Known times are aware and availability cannot exceed ingestion.
The fixture market's explicit last-update is its authored observation time, never
historical availability. Do not substitute bookmaker time, kickoff or ingestion
for missing observation/availability. This path exposes `SYNTHETIC_ONLY` usage
without backtest/execution claims even when tests supply known timestamps.

## Normalization and retained evidence

New versioned profile: at most 1 MiB raw JSON, 100 events, 20 bookmakers per event,
one supported market per bookmaker. Require exactly three distinct outcomes
matching explicit home/away guards and Draw. Reject duplicate keys/identities,
unsupported market keys, nonstandard numbers, malformed timestamps and incomplete
binding coverage. Uninterpreted additive metadata remains raw-only.

Require frozen bindings to existing soccer events and HOME/AWAY TEAM participants,
exact competition/team/start guards, source-scoped provider event keys, explicit
bookmaker-to-venue bindings and context versions. Reject event/venue collapse
within a capture and mismatched sources. Retain full binding values with output.
These are authored fixture bindings, not production mapping-review decisions.
Do not expand ADR-013 mapping targets or update events through event acceptance.

Verify retained raw bytes before parsing; validate the complete batch before
returning output. Ingestion owns candidates, receipt codec and acceptance port;
persistence implements the port. Retain raw reference/checksum/size/capture times,
full binding context, native event/bookmaker/market/outcome locators, canonical
output and parser/normalizer/context versions. Missing native quote IDs remain
null; tuple locators are not provider-issued IDs.

Quote identity includes raw capture identity, source-scoped native locator and
parser/normalizer/context versions, excluding price/output. Changed output under
the same identity conflicts; exact replay compares the full receipt and relational
values. A new capture creates new observations even if prices repeat. Never
overwrite earlier observations. Pin codec/identity golden vectors; array traversal
order must not determine identity within the same retained capture. Replay uses
retained context, not current mappings or mutable reference values.

## Transactional storage

Add an additive migration after `0010_soccer_receipts` for markets, selections,
observations and normalization receipts. Use restrictive typed FKs, uniqueness,
exact numeric storage, finite timestamps and immutable UPDATE/DELETE/TRUNCATE
guards on new retained records. Preserve all existing data/formats/envelopes.

Accept the complete capture in one caller-owned READ COMMITTED transaction.
Verify existing source/venue/event/participant context; never create references
implicitly. Serialize concurrent writers in deterministic canonical-ID order.
Compare conflicting inserts rather than updating. An encompassing savepoint must
remove all partial effects even when the caller catches an acceptance error.
The adapter never commits. Identical concurrent imports converge; differing
output/context conflicts. Readers reconstruct and validate retained values.
Direct SQL is not a supported reference-edit protocol or protection against an
owner disabling guards. Populated destructive migrations require human review.

Raw retention precedes database work; no S3 I/O spans write transactions. Rollback
may leave reusable raw objects. No distributed atomicity or durable quarantine is
claimed. This bounded path is synchronous persistence-only, like ADR-018's original
accept operation. Quote-driven workers/alerts will require a separate atomic outbox
contract before relying on publication. Historical Parquet, pruning/current-price
selection and correction policy remain separate work, not silently implemented by
this bounded observation store.

## Read-only API

Implement planned `GET /v1/events/{eventId}/markets` and
`GET /v1/markets/{marketId}/quotes`. Domain owns query ports, persistence owns
parameterized reads, API owns serialization. Include selections with markets;
quote results expose canonical IDs, separate source/venue, exact prices, timestamps
and normalization provenance, never raw bodies/storage configuration.
These are observations, not latest/best-price, historical `as_of` or pricing queries.

Default limit 50 (1..100), exclusive canonical-ID cursors, C-collation order,
`{items, next_after_market_id}` / `{items, next_after_quote_id}`. Fetch one extra
row for continuation. Cross-request pagination is not a frozen dataset/time order.
Read parent existence and results in one REPEATABLE READ, READ ONLY transaction.
Absent parent: 404; invalid input: 422; unconfigured/unavailable: sanitized 503;
programming errors remain server failures. Existing parents without data return
empty collections. Default app stays unconfigured; reuse ADR-024's explicit
loopback database composition. No auth/CORS/network/hosting policy changes.
Generate OpenAPI/TypeScript artifacts and verify additive compatibility.

## Incremental delivery and evidence

1. ADR, roadmap and index links; documentation checks and commit.
2. Domain identities/values, candidate codec, synthetic normalization and replay;
   network-disabled tests for golden identities, invalid odds/times/coverage,
   source/venue separation, raw integrity and retained-context determinism.
3. Migration and repository; disposable PostgreSQL round trips, reference errors,
   concurrent exact/conflicting retries, savepoint/outer rollback, immutable
   receipts and new observations preserving previous prices.
4. Read ports/API/local composition and generated contracts; pagination, errors,
   committed visibility, decimal fidelity and additive compatibility tests.
5. Local file -> Floci raw retention -> normalization -> PostgreSQL commit -> API.
   Verify exact raw bytes, all three prices/provenance, duplicate-free retries,
   retained replay, invalid final outcomes without partial writes and corruption
   failing closed. Run full `scripts/validate` before declaring the goal achieved.

Commit each independently reviewable increment. Routine tests remain authored,
credential-free and local. The existing Floci delivery-DLQ gap remains unresolved.
