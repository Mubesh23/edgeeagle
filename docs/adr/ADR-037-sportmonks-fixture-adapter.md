# ADR-037 — Fixture-first Sportmonks soccer fundamentals

**Status:** Accepted for bounded offline parsing, retained reads and reference resolution; writes deferred  
**Date:** 2026-09-24

## Context

The owner approved the next fixture-first Sportmonks increment after the bounded
[Odds API goal](ADR-035-odds-api-soccer-adapter.md). Sportmonks is already the
soccer-fundamentals direction in [ADR-011](ADR-011-data-provider-venue-strategy.md).
This decision does not choose a new provider or authorize live acquisition.

The existing [event acceptance](ADR-018-event-acceptance-lineage.md) operation is
initial-insert-only. It must not be repurposed into a multi-source event updater.
Associating Sportmonks observations with existing events requires a later explicit
receipt/acceptance contract, including correction and replay semantics. No existing
receipt format, API, database table or canonical identity changes in this increment.

## First supported subset

- Provider-native staging inside the existing Python ingestion library; no new
  deployable, universal adapter framework, dependency or domain provider import.
- One v3 football fixture-by-ID response, with `include=participants;state` and
  explicit UTC response metadata. This is not a list, pagination or season importer.
- Bounded UTF-8 JSON bytes (1 MiB), one `data` object and expected native fixture
  ID supplied by the caller. Native IDs are positive integer tokens bounded to
  signed 64-bit range; booleans, floats and numeric strings are rejected.
- Soccer `sport_id=1`, `state_id=1` with matching included `state.id=1` and
  `state.state=NS`, and non-placeholder fixture/participants. Other states fail
  explicitly rather than being coerced to scheduled or finished.
- Exactly two distinct participant IDs, one `meta.location=home` and one `away`.
  Array position and fixture display name do not determine roles. Preserve exact
  bounded participant names; no fuzzy matching, name splitting or canonical IDs.
- Require both `starting_at` in `YYYY-MM-DD HH:MM:SS` form and integral Unix-second
  `starting_at_timestamp`; interpret text only with `timezone=UTC` and reject
  disagreement. Kickoff must follow the caller's aware snapshot instant. That
  instant may be explicitly simulated; it is not authenticated capture evidence.
- Duplicate JSON keys, nonstandard/nonfinite numbers, malformed/missing fields,
  error envelopes, inconsistent identities/roles and oversized/deep input fail
  without returning a partial result. Unknown additive fields remain raw-only.
- Preserve native fixture/league/season/sport/state/participant IDs and UTC kickoff
  in immutable staging values. `venue_id` means physical stadium context, not an
  EdgeEagle market Venue, and is not mapped by this parser.

Parser version: `sportmonks-scheduled-fixture-json-v1`. This is an EdgeEagle
supported subset, not a claim that all legitimate provider responses fit it.
Missing participants or kickoff, other timezones, placeholders and non-NS states
require explicit subsequent support, never best-effort coercion.

## Evidence and limits

Tests use invented names, IDs and timestamps with `captured_at: null`; the fixture
sidecar records its simulated clock, request profile and documentation references.
No downloaded provider response, token or real subscription metadata is committed.
Provider schema references and verification dates live in the
[provider evaluation](../data/provider-evaluation.md#sportmonks-adapter-contract-review).

Retained-read composition must retain and verify raw bytes before parsing, using the
existing raw-store/offline boundaries. Parsing alone neither stores evidence nor
establishes provider rights, actual observation time or historical availability.
Kickoff, provider processing time, request time and subscription clocks must not be
substituted for `available_at`. No model-ready dataset or training inputs result.

Results, scores, statistics, lineups, injuries and xG are not normalized here.
xG remains a high-priority future feature, not a prerequisite for validating native
fixture identities. No odds, market Venue, pricing, risk or execution is introduced.
Real acquisition/capture retention requires separate human rights review; no free
plan or Football-Data-specific approval is generalized to Sportmonks.

## Capture manifest and retained-read boundary

`SportmonksCaptureManifest` binds an exact `RawPayloadReference` to the positive
native fixture ID and fixed `include=participants;state`, `timezone=UTC` request.
Its resource must equal `/v3/football/fixtures/{fixture_id}` without query strings
or credentials, and its declared byte size must fit the parser's 1 MiB limit.

- `AUTHORED_FIXTURE` requires an aware `simulated_snapshot_at`, null `captured_at`
  and no rights claim; usage is `SYNTHETIC_ONLY`.
- `PROVIDER_CAPTURE` requires aware actual `captured_at <= ingested_at`, no
  simulated clock, and a lowercase SHA-256 reference to separately reviewed rights
  evidence; usage is `REPLAY_ONLY`. A digest neither grants rights nor proves the
  evidence document exists or is authentic. Actual use still requires human review.
- Clocks normalize to UTC. Historical `available_at` must remain unknown in this
  bounded path; neither origin can produce model/backtest-eligible data.

`read_sportmonks_capture` reads the exact reference once and checks size and SHA-256
before invoking the parser with the declared fixture ID and snapshot instant.
Missing/corrupt bytes and unsupported payloads fail closed. It performs no raw
writes, acquisition, reference lookup or canonical transaction. Callers compose
existing `LocalFileImporter`, `ingest_raw` and `S3RawPayloadStore` for retention.
Provider identity stays in the raw reference; the source-scoped mapping boundary
verifies its registered source kind, not a hard-coded source ID.

This manifest is an in-memory declaration, not a persisted/versioned receipt or
automatic sidecar loader. The caller must retain its evidence; native parser output
alone is not durable replay provenance. No existing receipt format is changed.

## Read-only canonical-reference resolution

The next approved increment links verified native evidence to **preexisting**
canonical records. Reuse the ADR-025 five-role resolver for sport, competition,
season, home and away; add a Sportmonks-owned event/source wrapper. Provider
namespaces are `sport`, `league`, `season`, `participant` and `fixture`, with exact
positive native integer IDs encoded as decimal strings. Home/away keys come from
the parser's roles, not labels. The raw source ID scopes every key; its registered
record must have code `SPORTMONKS` and type `SPORTS_DATA`.

Resolve all six complete histories under ADR-013 at one explicit aware mapping
cutoff. Missing, revoked, future-only, malformed or wrong-type mappings fail.
Validate canonical hierarchy, distinct soccer TEAM participants and exact event
HOME/AWAY attachments. Names may differ across providers; there is no fuzzy match
or confidence threshold. Recorded review metadata is not reviewer authentication.

`normalize_sportmonks_capture` verifies retained raw bytes **before** one reference
read context, then returns an immutable in-memory `NormalizedSportmonksFixture`
containing the manifest, native fixture, selected canonical context, all six
revisions, UTC mapping cutoff, parser version and normalizer version
`sportmonks-scheduled-fixture-mappings-v1`. The result is staging evidence, not an
ADR-018 event candidate, durable receipt or accepted write command.

For this bounded path, canonical status must be `SCHEDULED`, kickoff must exactly
match the native UTC instant, and kickoff must fall within the canonical season.
Disagreement fails rather than choosing a source, tolerating drift or updating an
event. Correction/rescheduling and other lifecycle states require a later contract.
The mapping cutoff may differ from the capture clock; selected current records are
not historically available context. Existing unknown availability/usage limits hold.

All repositories must share a pinned read-only snapshot. The port cannot prove
transaction isolation or complete supplied history; concrete PostgreSQL composition
must enforce REPEATABLE READ/read-only before this is used against stored mappings.
It must close before returning the candidate; raw-store I/O never spans that
transaction. No retries, mapping registration, canonical creation/update, outbox,
API change or reuse of Odds API receipt serialization is introduced.

## Delivery and validation

1. Record this subset and provider references before code.
2. Add authored single-fixture data and a pure parser with network-disabled tests:
   roles/order, IDs, kickoff agreement, malformed inputs, unsupported state and bounds.
3. Add an explicit capture manifest/retained-read boundary; then, separately,
   source-scoped mapping resolution. League, season, participant and event references
   must be verified; no auto-creation or fuzzy mapping.
4. Later: review receipt/storage/correction compatibility before canonical writes,
   then deterministic retained replay and read-only consumers. Reuse infrastructure,
   not the provider-specific Odds API receipt format.

Use existing root tooling, targeted pytest/coverage, Ruff/mypy, documentation link
checks and full `scripts/validate` before handoff. Live provider contract tests and
HTTP acquisition are separate opt-in work, not routine validation dependencies.

## Implementation status

The pure scheduled-fixture parser and authored fixture are implemented with
67 network-disabled tests and 100% parser statement coverage. Tests cover native
identity bounds, exact roles independent of ordering, UTC/Unix agreement,
snapshot cutoffs, missing/unsupported data, error envelopes and malformed JSON.
The capture manifest and integrity-checked retained reader are also implemented,
with 34 additional offline tests and 100% manifest statement coverage. A local
Floci test composes authored-file retention, repeat reads, idempotent raw storage
and rejection of missing/corrupt objects. Even provider-origin test declarations
use invented data and evidence hashes; no actual capture approval is claimed.
Port-level source-scoped reference resolution and retained-capture normalization
are implemented with offline failure-path tests. Concrete pinned PostgreSQL
composition, durable receipts and downstream integration remain deferred;
this is not completion of the Sportmonks adapter.

Full `scripts/validate` passed locally on 2026-09-24 after the retained-reader
increment: 1,265 Python unit tests, 179 integration tests plus the documented strict
Floci delivery-DLQ expected
failure, generated-artifact checks, formatting/lint/types, package tests, contract
compatibility, credential-free synthesis, advisory scans and builds. Hosted CI,
fresh-checkout and live provider validation were not run for this increment.
