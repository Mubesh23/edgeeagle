# Implementation Roadmap

**Status:** Draft

## Delivery and commit policy

Each phase is implemented as a sequence of small, coherent, independently reviewable increments. **Incremental commits are required; a phase must not be accumulated into one final commit.** All commits use Conventional Commits as defined in `AGENTS.md` and the monorepo engineering guide.

An increment should be validated with the cheapest relevant checks before it is committed. Foundational contracts and primitives should generally land before their consumers. Tests and documentation that define or prove the same change should normally travel with that change. Architectural decisions that must precede implementation may be committed first as ADR/documentation changes.

At phase exit, `scripts/validate` (or the strongest validation then available) must pass unless the roadmap explicitly states otherwise, and any skipped check must be reported.

## Phase 0 — Documentation & Architecture Baseline

Deliver:

- PRD v0.5
- TDD v0.2
- ADRs
- provider matrix
- canonical domain model
- ingestion design
- API/MCP design
- local testing strategy
- cost/quota strategy
- monorepo guide

Exit: unresolved foundational decisions are explicit rather than hidden.

## Phase 1 — Repository Foundation

- Create monorepo workspaces
- Root scripts
- Root AGENTS/CLAUDE
- CI
- API/web/mobile/MCP skeletons
- PostgreSQL migration framework
- Floci local environment
- Mock provider server
- CDK skeleton

Exit: `scripts/validate` succeeds on a fresh checkout with no AWS credentials or paid provider calls.

## Phase 2 — Canonical Domain & Ingestion

- Core schemas/DB entities
- source/venue mappings
- raw S3 abstraction
- provider adapter framework
- entity resolution
- event envelope/idempotency

Exit: a fixture can flow raw -> canonical -> event -> API.

Local acceptance evidence: `scripts/test-integration -k fixture_raw_to_api`
now exercises both legacy bindings and mapping-backed manifests using retained synthetic bytes,
PostgreSQL, Floci S3/EventBridge/SQS, and the in-process FastAPI boundary. Exact
reingestion and real duplicate broker delivery leave one canonical event and
one consumer verification receipt. This demonstrates the narrow fixture-flow
exit criterion, not completion of every Phase 2 capability or production readiness.
Real-provider identity/review workflows, historical datasets, worker supervision,
and the known EventBridge delivery-DLQ emulator gap remain explicit follow-ups.
The read-only fixture reference resolver now selects canonical references and
retains mapping-revision evidence through normalization and format-2 receipts,
without rewriting legacy receipts. Pinned PostgreSQL resolution and both paths
through the fixture-to-API acceptance test are implemented under
[ADR-025](../adr/ADR-025-mapping-backed-fixture-context.md). Explicit authored
event identity, labels, status, and reference keys remain necessary fixture context.
Read-only mapped-receipt replay now reproduces complete retained captures without
current mapping reads, checks supported versions and full candidate equality, and
survives later mapping revocation/reference edits. This is reproducibility evidence,
not authorization for fresh ingestion or a historically eligible dataset.
The next snapshot increment is contract-first:
[ADR-026](../adr/ADR-026-replay-dataset-manifest.md) and its
[manifest specification](../architecture/dataset-snapshot-manifest.md) define a
bounded, content-versioned collection of complete captures and mapped receipts.
Frozen values, strict serialization, content hashes, and offline golden vectors
are implemented. This replay-only metadata contract does not complete historical
datasets or permit backtesting. Read-only complete-snapshot verification now composes
the strict codec with retained capture replay, with no partial success or writes.
Local tests cover accepted receipts after reference edits and final-artifact loss
or corruption. Manifest cataloging and historical availability evidence
remain separate design/implementation work.
[ADR-027](../adr/ADR-027-replay-manifest-storage.md) now defines the narrow immutable
manifest-storage port and S3 layout. The port/adapter now implements conditional
writes and strict bounded reads, with offline and Floci integrity/idempotency tests.
No catalog or production storage resources are added. Retrieve-by-version replay
composition now verifies retained receipts and raw artifacts after current-state
edits, while distinguishing missing manifests from lost raw artifacts.

The first narrow catalog is now a private local operator interface under
[ADR-031](../adr/ADR-031-local-dataset-catalog.md): explicitly pinned ADR-029 roots
can be listed and freshly inspected with provenance and replay-only restrictions.
It adds no SQL catalog, UI exposure, historical eligibility or provider calls;
older manifest formats and production catalog publication remain separate work.
The additive [ADR-032](../adr/ADR-032-local-dataset-api.md) local HTTP consumer now
supports listing and fresh inspection through the generated client contract,
with explicit opt-in configuration and no hosted access or authentication changes.
The [ADR-033](../adr/ADR-033-private-dataset-browser.md) local web consumer now
shows retained provenance and replay-only warnings with explicit fresh inspection.
This is a private data-foundation view, not completion of the Phase 8 terminal.

## Phase 3 — V1 Provider Adapters

Completed bounded provider goal: [ADR-035](../adr/ADR-035-odds-api-soccer-adapter.md) defines
a fixture-first The Odds API pre-match soccer 1X2 adapter, retained mapping evidence,
idempotent persistence and read-only API results. The user approved extending the
existing quote usage response to distinguish synthetic and replay-only captures;
the offline path is implemented through whole-capture receipts, immutable storage,
atomic acceptance and snapshot-consistent API reads. Authored end-to-end tests
cover replay after mapping correction/revocation and reject corrupt raw evidence.
Full `scripts/validate` passed locally on 2026-09-24 (1,164 Python unit tests;
178 integration tests plus the known strict Floci delivery-DLQ expected failure).
This closes the fixture-first goal, not Phase 3's multi-provider exit. Real capture
rights/settlement evidence, explicit provider contract tests and historically
eligible datasets remain separate gates. No live calls or licensing changes are
authorized by this completion.

Active market-foundation goal: [ADR-034](../adr/ADR-034-synthetic-market-quotes.md)
defines authored soccer 1X2 ingestion through retained raw provenance, canonical
markets/selections/quote observations, atomic idempotent persistence and bounded
read-only API results. Pure domain values and market/selection identities are
implemented, alongside retained fixture normalization, replay and strict versioned
receipt serialization, an additive PostgreSQL schema and transactional acceptance.
Bounded domain read ports and snapshot-consistent PostgreSQL market/quote queries
and HTTP endpoints with generated contracts are implemented. The complete authored
raw-to-API composition and full `scripts/validate` passed locally (983 Python unit
tests; 160 integration tests plus the known Floci delivery-DLQ expected failure).
This completes the bounded authored fixture goal, not the multi-provider phase.
This fills a missing Phase 2 market slice before real-provider adapters, not model
pricing, executable-price selection or historical backtest eligibility.

First bounded goal: [ADR-028](../adr/ADR-028-football-data-results-import.md) defines
a local Football-Data results CSV import with retained raw bytes, additive score
receipts, stored replay snapshots, and authored offline fixtures. This bounded
workflow is implemented and exercised with disposable PostgreSQL/Floci, including
concurrent retries, batch rollback and retained-context replay. It excludes odds,
full archives, cataloging, historical eligibility,
provider downloads/licensing approval, and production resources.
This completes the local results-import goal, not Phase 3's multi-provider exit.
Next: review evidence/rights and availability requirements for a real research
dataset before expanding supported file shapes or starting model training.

- Football-Data.co.uk importer
- Sportmonks free-tier adapter
- The Odds API free-tier adapter
- Kalshi market-data/demo adapter
- Polymarket market-data adapter

Exit: contract tests pass within free/demo budgets and canonical market/event mapping is demonstrated.

## Phase 4 — Soccer Model

Follow [ADR-008](../adr/ADR-008-soccer-baseline-model.md) and
[ADR-036](../adr/ADR-036-soccer-model-evaluation-and-market-benchmarking.md).
This is future research scope; the active Phase 3 adapter goal remains unchanged.

- Dataset/rights/data-quality and point-in-time availability analysis, including
  missing coverage, reference dependencies and outcome/feature separation. Current
  replay-only snapshots cannot be used for model training/backtest decisions;
  establish an eligible research dataset contract first.
- Define versioned forecast horizons and as-known kickoff/cutoff policies.
- Reproducible no-vig market-consensus baseline with coverage and de-vig sensitivity.
  Bring forward only the deterministic research pricing/de-vig slice needed for
  this comparison; Phase 5 reuses it, not a second implementation.
- Elo/simple team-strength probability baseline; independent Poisson; Dixon-Coles.
- Evaluate dynamic/bivariate Poisson challengers; prioritize xG/xGA-enhanced models
  when rights and eligible data support them. Goals/results-only baseline first
  is permitted. Richer/Bayesian statistical models require justification.
- Competition-aware chronological recency/feature/model selection, calibration,
  explicit uncertainty representation and frozen OOS comparison framework.
- Model registry/artifact persistence with family, market dependencies, feature,
  dataset, horizon, calibration and evaluation lineage.
- ML challengers only after statistical baselines; market-aware challengers remain
  distinguishable; calibrated ensembles only if repeatable OOS evidence justifies.

Exit: reproducible chronological OOS evaluation on frozen eligible datasets reports
performance against documented statistical and no-vig market baselines, including
coverage, calibration, uncertainty limitations and negative findings. Every promoted
model demonstrates robust incremental performance under the declared policy.
Not every challenger must be implemented or beat the market; the phase can complete
with no challenger promoted. Unavailable benchmark data is a recorded prerequisite
gap, not a pass or permission to use hindsight prices.

## Phase 5 — Pricing & Opportunity Engine

- Market pricers
- versioned pluggable de-vig methods, reusing the Phase 4 research baseline
- raw EV versus uncertainty-aware strategy qualification/actionable edge
- quote freshness/executability model
- opportunity queries

Exit: model-vs-market results available through API.

## Phase 6 — Backtesting & Strategy

- strategy representation
- simulated clock
- execution assumptions
- walk-forward runs
- log loss/Brier/calibration and paired simple/market baseline comparisons
- CLV (diagnostic, not proof of profit), ROI/P&L, drawdown, volatility and sample count
- horizon/league/season/market/odds/selection segments and confidence intervals
- fractional Kelly as the preferred sizing research benchmark under exposure/loss/model-quality constraints,
  not full Kelly or an automatic production default

Exit: leakage tests and deterministic regression fixtures pass.

## Phase 7 — Paper Portfolio & Risk

- cash ledger
- positions
- settlement
- risk limits
- paper execution adapter

Exit: paper positions reconcile exactly from ledger/events.

## Phase 8 — API/MCP + Web Terminal

- Discover
- Event Terminal
- Portfolio
- Watchlists/alerts
- Backtests
- Agent/MCP tools

Exit: complete desktop research-to-paper loop.

## Phase 9 — Mobile

- Discover
- Event details
- Watchlist
- Portfolio
- Alerts/deep links
- Agent
- paper position actions

Exit: cross-device state continuity demonstrated.

## Phase 10 — Parlays

- independent-event pricing
- soccer same-event pricing from score distribution
- prefer exact score-matrix enumeration for fully covered soccer legs
- joint-model coverage and uncertainty, including simulation and mixed-group assumptions
- unsupported correlated pricing returns no invented joint probability/EV
- correlation warnings, tail/settlement checks and deterministic coverage tests

## Phase 11 — Additional Sports

Basketball -> American football -> Tennis based on provider coverage and model readiness.

## Phase 12 — Controlled Execution

Only after paper/backtest/research validation:

- execution permissions
- prepare/confirm/submit lifecycle
- venue adapter against test/demo where available
- fees/liquidity/slippage
- kill switches and audit
