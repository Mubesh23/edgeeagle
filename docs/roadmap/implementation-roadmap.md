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
now exercises this path using retained synthetic bytes, explicit fixture bindings,
PostgreSQL, Floci S3/EventBridge/SQS, and the in-process FastAPI boundary. Exact
reingestion and real duplicate broker delivery leave one canonical event and
one consumer verification receipt. This demonstrates the narrow fixture-flow
exit criterion, not completion of every Phase 2 capability or production readiness.
Dynamic provider-mapping integration, historical datasets, worker supervision,
and the known EventBridge delivery-DLQ emulator gap remain explicit follow-ups.

## Phase 3 — V1 Provider Adapters

- Football-Data.co.uk importer
- Sportmonks free-tier adapter
- The Odds API free-tier adapter
- Kalshi market-data/demo adapter
- Polymarket market-data adapter

Exit: contract tests pass within free/demo budgets and canonical market/event mapping is demonstrated.

## Phase 4 — Soccer Model

- Data quality notebook/analysis
- Baseline team strength
- score distribution
- calibration/evaluation
- model registry/artifact persistence

Exit: reproducible OOS metrics on frozen datasets.

## Phase 5 — Pricing & Opportunity Engine

- Market pricers
- de-vig methods
- EV/edge
- quote freshness/executability model
- opportunity queries

Exit: model-vs-market results available through API.

## Phase 6 — Backtesting & Strategy

- strategy representation
- simulated clock
- execution assumptions
- walk-forward runs
- CLV/calibration/drawdown metrics

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
- correlation warnings

## Phase 11 — Additional Sports

Basketball -> American football -> Tennis based on provider coverage and model readiness.

## Phase 12 — Controlled Execution

Only after paper/backtest/research validation:

- execution permissions
- prepare/confirm/submit lifecycle
- venue adapter against test/demo where available
- fees/liquidity/slippage
- kill switches and audit
