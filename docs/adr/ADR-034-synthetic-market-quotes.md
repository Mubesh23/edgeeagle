# ADR-034 — Retained synthetic market and quote ingestion

**Status:** Accepted; end-to-end authored fixture goal implemented and locally validated  
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

## Implementation evidence

`edgeeagle_domain.markets` implements frozen values, semantic market/selection
identities and complete three-way selection validation. Identity v1 uses the exact
objects `{identity_version: 1, event_id, market_type, period}` and
`{identity_version: 1, market_id, outcome}` in sorted-key compact ASCII JSON;
IDs are lowercase SHA-256 hex. Tests pin independent preimages for these identities.
Quote IDs remain caller-supplied typed values until ingestion allocates them.
Run the domain tests for identity, immutable values, exact Decimal prices, unknown
and UTC timestamps, wrong ID types and invalid/incomplete market membership.
This is the domain prerequisite, not a functioning ingestion or API path.

`edgeeagle_ingestion.synthetic_markets` now reads an integrity-checked retained
capture, validates explicit `MarketFixtureBinding`/`VenueBinding` context and
returns complete immutable candidates. Parser `synthetic-market-json-v1` and
normalizer `synthetic-market-bindings-v1` allocate source/capture/locator/version
quote identities, preserving Decimal values and unknown availability. Sources must
explicitly declare the `SYNTHETIC_FIXTURE` capability; this is a caller assertion,
not authentication or live-provider compatibility. Read-only replay uses retained
bindings and compares complete projections without current-state reads.
Network-disabled `tests/unit/test_market_normalization.py` covers retention,
malformed/duplicate/incomplete data, context mismatches and replay drift. The
receipt codec below builds on this path; PostgreSQL acceptance and API remain pending.

The ingestion-owned `market_receipts` codec now serializes one complete bookmaker
candidate with envelope `{format: 1, usage: SYNTHETIC_ONLY, parser_version,
normalizer_version, candidate}`. The candidate contains full dataclass field
names, typed-ID value objects, retained bindings/raw provenance, selections and
quotes. Derived market/selection IDs are reconstructed from validated semantics.
The maximum encoded receipt is 1 MiB; oversize reads fail before JSON parsing.
Encoding uses sorted compact ASCII JSON, UTC ISO times, enum strings, sorted
capabilities/venue bindings/selections/quotes and exact canonical Decimal strings.
Decimal coefficient/exponent normalization is independent of ambient precision
and avoids exponent-sized fixed-point allocation. No numeric rounding is allowed.

Decode requires exact fields at every record, supported envelope versions, valid
typed constructors and byte-for-byte canonical re-encoding. Duplicate keys,
nonstandard/floating JSON numbers, malformed scalars and collections fail closed.
The authored fixture's canonical receipt SHA-256 is pinned in offline tests;
round trips remain replayable without current-state reads. This is a structural
receipt codec, not evidence of database acceptance, complete capture coverage,
artifact retention, live data authenticity or research eligibility. PostgreSQL
acceptance and API integration remain pending.

Migration `0011_market_quotes` adds four immutable tables with restrictive
references and exact numeric quote observations. Composite FKs prevent a quote
from disagreeing with its receipt's market/source/venue or its selection's market.
Canonical receipt bytes are stored as text (not JSONB reserialization), with a
1 MiB bound and envelope/source checks. Full canonical decoding, event-role
consistency, three-outcome completeness and idempotent batch comparison belong to
the upcoming repository; SQL constraints alone do not establish these guarantees.
Quote native IDs are null for this initial synthetic profile. New provider/codec
versions require an explicit additive rollout rather than silently accepting them.
Downgrade removes only the new tables/function and requires review for populated
non-test databases. Tests cover offline SQL, exact numeric storage, cross-reference
rejection, immutability and disposable upgrade/downgrade/reapply with prior data
preserved. No application database is automatically migrated.

The ingestion-owned `market_acceptance` port and PostgreSQL `markets` adapter now
accept canonicalized batches in a caller-owned READ COMMITTED transaction. Receipt
identity is SHA-256 of sorted compact ASCII JSON containing `identity_version: 1`
and sorted `quote_ids`; prices are excluded from identity but included in full
comparison. Exact retries return zero newly inserted receipts; changed output
under the same identity conflicts. Sorted event locks serialize supported writers;
an encompassing savepoint rolls back the entire batch on failure. Existing
reference context is checked, never implicitly inserted or updated.

Retained reads validate receipt identity and every relational projection without
consulting current reference names; fresh acceptance rejects reference drift.
Batch validation checks bounded size, shared capture and complete bookmaker
bindings. It cannot establish that no event was omitted from raw input: application
composition must normalize/replay the complete retained capture before opening the
write transaction. No S3 I/O or commit occurs inside the repository.

Offline identity tests and disposable PostgreSQL tests exercise exact/concurrent
retries, conflicting writers, new captures, commit visibility, outer rollback,
reference drift and injected late failures across one and two bookmaker receipts.
Read-only API and complete raw-to-API composition remain pending.

Domain `market_query` now defines bounded market/quote queries, immutable read
results and the `MarketReader` port. Persistence `PostgresMarketReader` requires
an active REPEATABLE READ, READ ONLY transaction. Parent checks and page reads
share that snapshot; missing parents return `None`, existing empty parents return
empty pages. Parameterized exclusive-ID reads fetch at most limit plus one rows;
the schema's C-collated ID indexes determine order, not observation time.

Market pages include validated canonical selections. Quote pages validate retained
receipts and their relational projections, caching each receipt within the page,
then expose exact Decimal observations with raw capture identity and native
locators/parser/normalizer/context versions. They perform no S3 access and do not
consult current reference names. Corrupt quote projections fail closed, not as
empty results. Tests cover paging, absent/empty parents, source provenance, exact
long decimals, reference-name drift and snapshots excluding later commits.
HTTP serialization, local API composition and end-to-end raw-to-API tests remain
pending; these read ports alone do not complete the goal.

The two GET endpoints now serialize these read ports through the existing explicit
loopback PostgreSQL factory. The default app remains unconfigured. Generated
OpenAPI and TypeScript artifacts include market selections, decimal-string quote
prices and nested provenance (raw capture/checksum/size, native locators and
normalization versions), without raw bodies or storage configuration. Unit tests
cover boundary validation, 404/503/500 behavior, read-only methods and exact decimal
serialization; disposable PostgreSQL-to-HTTP tests cover committed visibility,
pagination, provenance and unchanged results after an exact acceptance retry.
Complete local-file/Floci-to-API composition and full validation remain pending.

`market_import.import_market_fixture` now composes local acquisition/raw retention,
full-capture normalization and canonicalization before entering a caller-provided
acceptance transaction. It verifies retained readback before commit and returns
raw identity, receipt IDs and insertion count only after successful context exit.
The caller supplies matching pre-existing references and a commit/rollback context;
no storage I/O spans canonical writes. Unit tests verify ordering, mismatched
readback and commit failures. End-to-end `market_fixture_raw_to_api` tests use the
authored fixture, disposable Floci bucket/PostgreSQL database and actual HTTP
composition to prove exact raw retention, all three prices/provenance, exact and
concurrent retries, retained replay after reference edits and fail-closed replay
for missing/corrupt raw. `market_import_bad` proves invalid final outcomes retain
raw without partial canonical effects or opening a write transaction.
Ordinary quote reads remain available after raw loss: they expose retained
observations, not a fresh raw-verification or backtest-eligibility claim.
Full `scripts/validate` remains the completion gate.

Completion evidence (2026-09-23): `scripts/validate` passed with 983 Python unit
tests, 160 integration tests and the existing strict expected failure for Floci
EventBridge delivery-DLQ forwarding. Generated drift/compatibility, formatting,
lint, typechecks, lock consistency, Node/application tests, credential-free CDK
synthesis, dependency advisory scans and builds passed. Scoped workflow and HTTP
tests report 100% branch coverage; the query adapter reports 91%, not complete
coverage of defensive corruption paths. Existing Starlette deprecations and the
resource-free CDK template warning remain. Some unchanged Turbo tasks used local
cache. Hosted CI/fresh-checkout and browser verification were not run for this
backend-only goal; no push or production deployment was performed.

This completes only the bounded authored market fixture goal. Live provider
adapters, supported production mapping review, market-driven outbox workflows,
executable-price selection, modeling and backtest eligibility remain separate.
