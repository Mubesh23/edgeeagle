# ADR-035 — Fixture-first The Odds API soccer odds adapter

**Status:** Accepted; pre-release API extension approved; implementation in progress  
**Date:** 2026-09-23

## Goal

Implement a fixture-first The Odds API adapter for pre-match soccer 1X2 odds,
retaining provenance and explicit canonical mappings, with idempotent PostgreSQL
storage and read-only API results. Normal tests require no provider credentials
or calls. This is the next bounded Phase 3 increment, not completion of Phase 3.

## Existing constraints and discovered differences

[ADR-034](ADR-034-synthetic-market-quotes.md) deliberately pins synthetic parser,
normalizer, receipt format and usage. Its fixture binding requires a synthetic
source capability. Do not remove these checks to pass real provider data through
that adapter, rewrite old receipts, or change legacy quote identities.

The existing quote API promises `usage: SYNTHETIC_ONLY` as an OpenAPI constant.
A diagnostic comparison of the current contract with a proposed
`SYNTHETIC_ONLY | REPLAY_ONLY` usage enum fails the pinned comparator with
`response-property-const-removed` and `response-property-enum-value-added` errors.
The foundation checkpoint predates these endpoints and cannot detect this
particular regression. Passing that checkpoint alone is insufficient evidence.

Provider contract observations are recorded with sources and a verification date
in [the provider evaluation](../data/provider-evaluation.md#odds-api-adapter-contract-review).
The standard bookmaker timestamp differs from the synthetic market-level
timestamp; source timestamp scope must be retained explicitly. Provider response
shape alone does not prove that a game is pre-match or historically available.

## Decision

- Add a separate versioned provider parser/normalizer and retained candidate
  format; reuse canonical Market/Selection/Quote values and transactional rules.
  Roll out readers and additive schema support before enabling new-format writes.
  Keep old bytes, identifiers, immutable guards and records unchanged. A downgrade
  must refuse when new-format records exist rather than delete or convert them.
- Accept bounded retained decimal/ISO soccer `h2h` captures with an explicit
  request/capture manifest. Require the HOME/DRAW/AWAY outcome set and explicit
  regulation-time semantics for the supported sportsbook profile. Reject other
  markets, exchange/lay prices and ambiguous period semantics; do not silently
  reinterpret them. Define empty/no-quote responses as valid zero-observation
  captures, distinct from malformed or incomplete three-way markets.
- Resolve source-scoped provider event IDs and bookmaker keys through existing
  mapping histories, using one REPEATABLE READ, read-only reference snapshot.
  Events and venues must already exist. Retain selected revisions, cutoff,
  canonical event/participant context and exact provider-label guards. No fuzzy
  matching, implicit event creation, reviewer authentication or mapping-write UI.
  Labels are guards, not invented provider participant IDs.
- Require an explicit capture instant and compare kickoff against it; a current
  scheduled status or a provider query filter alone is insufficient. Preserve
  capture evidence, unknown availability and the provider timestamp's scope.
  Authored fixtures must remain distinguishable from actual provider captures.
  Neither category becomes executable or backtest-eligible through this adapter.
- Retain raw bytes before parsing. Finish whole-capture validation and mapping
  resolution before opening the write transaction. Store exact Decimal prices,
  full versioned evidence and immutable observations; no S3 I/O spans writes.
  Compare full projections on retry, with deterministic locks and batch rollback.
  Replay retained evidence without current mappings after correction/revocation.
- Use authored, clearly labelled provider-shaped fixtures and mock responses for
  routine tests. Support privately retained captures only with explicit rights
  provenance; do not acquire or redistribute real data under assumed permission.
  A separately invoked bounded contract check must never run in routine validation.
  Any future HTTP acquisition must redact keys, bound response size/time/calls,
  retain request identity without secrets and expose quota headers; no hidden retries.
- Preserve the API's domain query boundary and decimal-string prices. Expose
  origin, usage, mapping/version and timestamp-scope provenance without raw bodies,
  credentials or storage configuration. No pricing, EV, execution, auth/CORS,
  deployment, outbox or live/in-play revaluation changes are included.

## Approved API compatibility exception

The user explicitly approved extending the existing endpoint on 2026-09-23.
Permit the deliberate pre-release change from the usage constant SYNTHETIC_ONLY
to the enum SYNTHETIC_ONLY | REPLAY_ONLY and regenerate clients together. Existing
synthetic records and receipt identities remain unchanged; genuine captures must
never be labelled synthetic. Do not introduce a duplicate versioned endpoint.

The exception covers only this response-value expansion, not arbitrary breaking
changes. Compare against the preceding contract as well as the foundation
checkpoint, account explicitly for the known const-removal/enum-addition findings,
and reject unrelated breaks. Do not weaken the comparator or rewrite the frozen
foundation checkpoint. No permission to spend quota, use credentials or assert
licensing follows from this API approval. Those decisions remain separate.

## Incremental implementation and acceptance

1. Record the approved API choice and finalize this ADR; validate documentation links.
2. Provider parsing and authored fixtures: offline tests for response bounds,
   duplicates, exact decimals, empty results, unsupported markets and pre-match
   checks. Commit independently.
3. Mapping resolution and retained evidence/codec: missing, revoked, wrong-type,
   changed and ambiguous context fail closed; replay preserves original context.
4. Additive persistence and reader rollout: preserve legacy golden bytes, test
   migration guards, concurrency, exact retries and whole-batch rollback in
   disposable PostgreSQL. No developer application database is auto-migrated.
5. Implement the approved API contract, regenerate artifacts and compare both
   the preceding contract and foundation checkpoint; test decimal fidelity,
   pagination, origin/usage, sanitized errors and local read-only composition.
6. Compose retained fixture -> Floci -> mapping snapshot -> normalization ->
   PostgreSQL -> API. Prove all three prices/provenance, duplicate-free retries,
   retained replay after mapping corrections and no partial acceptance on errors.
   Document the opt-in provider-contract tier separately from offline validation.
7. Run `scripts/validate`; report actual local evidence, unrun live/hosted checks,
   remaining emulator limitations and all incremental Conventional Commits.

The goal is incomplete until the entire adapter-to-API path passes. A parser,
mock HTTP response or synthetic-adapter rename alone does not satisfy it.

## Implementation evidence

The provider-native parser `edgeeagle_ingestion.odds_api_parser` now implements
version `the-odds-api-soccer-h2h-json-v1`. It accepts UTF-8 JSON up to 1 MiB,
0..100 events and 0..20 bookmakers per event, with at most one h2h market per
bookmaker. Empty event/bookmaker/market collections are valid no-quote results;
a present market must have exactly the three expected distinct outcomes. Native
IDs/labels are bounded nonblank unpadded text. Duplicate JSON keys/identities,
line-bearing or unsupported markets, nonfinite/nondecimal/invalid prices,
malformed timestamps and mismatched competition keys fail the whole parse.

The caller supplies an explicit aware snapshot instant; every kickoff must be
strictly later. Known bookmaker and market update times are retained separately,
normalized to UTC and rejected if later than that instant; neither is promoted
to availability. Both may remain unknown. These checks do not authenticate capture
evidence or approve bookmaker settlement rules: provenance and canonical mapping
remain subsequent stages. Parsing sorts native results deterministically and has
no storage, database, HTTP or credential access. Legacy synthetic parsing is unchanged.

The new authored fixture at `tests/fixtures/providers/the_odds_api/pre-match-v1/`
uses the standard bookmaker-level timestamp shape; its metadata explicitly sets
`captured_at: null` and a separate simulated snapshot time. It is not a downloaded
provider response. Offline tests cover exact long decimals, empty results,
pre-match boundaries, malformed/duplicate data, size/text limits and ordering.
The parser's 49 tests report 100% branch coverage. Parser success alone does not
certify live provider compatibility.

The read-only `odds_references` resolver now selects source-scoped competition,
event and bookmaker mappings and returns immutable canonical context with full
revision evidence and UTC cutoff. Canonical hierarchy, soccer HOME/AWAY teams,
The Odds API source, sportsbook venues and non-collapsing mappings are validated.
It performs no implicit writes or label-based identity inference. PostgreSQL
composition pins all repositories to one REPEATABLE READ, read-only transaction
with bounded SQL and idle waits. Tests prove a concurrent revocation leaves an
existing snapshot unchanged and fails a fresh read; offline tests cover corrected
mapping selection, unavailable references and evidence validation.

This evidence is not yet serialized or wired into quote acceptance. Exact provider
label guards, capture/rights provenance, settlement profiles, versioned receipts,
database rollout, API extension and end-to-end goal validation remain pending.
