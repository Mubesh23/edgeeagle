# Foundation readiness review

Reviewed: 2026-09-22. Scope: roadmap Phase 1, delivered incrementally.

## Initial inspection

The supplied directory contains AGENTS.md, CLAUDE.md, 25 documentation files,
an empty scripts directory, and a local .DS_Store. There is no Git repository,
application source, package configuration, lockfile, CI, or executable root script.
Preserve the supplied documents as the baseline; ignore the local .DS_Store.

Read AGENTS.md, CLAUDE.md, the documentation index, PRD, TDD, canonical domain
model, provider evaluation, roadmap, all 12 ADRs, ingestion design, API/MCP
design, local testing strategy, monorepo guide, cost strategy, reference patterns,
and Parlay Lab specification before implementation.

Available tools: Node 20.20.1, Corepack 0.34.6, uv 0.7.3, Python 3.11.5,
Docker CLI 20.10.22, and Git with an existing author identity. Standalone pnpm
is absent. Docker server inspection failed; local container readiness is unverified.
No provider or AWS credential is needed for the initial workspace work.

## Repository understanding

EdgeEagle transforms sports data into outcome distributions, fair prices, market
comparisons, deterministic strategies, risk checks, and paper/eventual execution.
It is a research terminal, not a picks application. The initial sport is soccer.

Bounded contexts comprise canonical sports/market data and ingestion; modeling;
pricing/opportunities; strategies/backtesting; portfolio/ledger/risk; watchlists
and alerts; paper/eventual execution; and client/API/MCP experience adapters.

Use a polyglot modular monolith plus async jobs, with independent deployment when
justified. Applications depend on application/domain libraries. Domain logic
must not import FastAPI, database clients, AWS/provider SDKs, or React. Adapters
implement inward-owned interfaces. Python owns authoritative analytical/backend
logic; TypeScript owns React/Vite web, Expo mobile, MCP, and CDK. OpenAPI and
versioned event contracts connect boundaries; generated clients are protected.

PostgreSQL holds operational state. S3/Parquet holds raw and historical data,
versioned datasets, model artifacts, and research results. EventBridge routes
events to per-consumer SQS queues with DLQs and idempotent consumers. Batch
pregame inference persists predictions. There is no new service extraction,
Redis, OpenSearch, Kafka, Kubernetes, or online model server in this foundation.

Sportmonks, The Odds API, Kalshi, Polymarket, and Football-Data.co.uk remain the
initial source direction behind adapters. DataSource and Venue are distinct.
Provider pricing is a dated repository snapshot, not reverified in this review.
No provider calls or licensing assumptions are necessary for synthetic fixtures.

Normal tests use no paid APIs or real AWS credentials: network-free unit tests,
fixtures/mocks, then PostgreSQL/Floci integration. Optional provider contracts
are separate and budgeted. Backtests use available_at and retained snapshots.
Models output distributions; pricing, EV, risk, settlement, and parlay evaluation
are authoritative backend capabilities. MCP and agents consume those results.

Each coherent increment is reviewed, validated, documented, and committed using
Conventional Commits before the next increment. Never push, deploy, rewrite
shared history, or discard user work as part of local foundation implementation.

## Conflicts and open decisions

- ADR-001 and ADR-012 are accepted; ADR-002 through ADR-011 are proposed.
  The user's session instructions explicitly authorize the listed foundation
  technologies. Preserve ADR status; do not claim formal acceptance.
- TDD section 45 includes event-envelope/idempotency/DLQ tests in technical
  foundation, while roadmap Phase 2 owns event envelopes/idempotency. Follow
  roadmap sequencing: Phase 1 builds runnable shells and local infrastructure;
  actual consumers and their behavioral gates arrive in Phase 2. The broader
  TDD foundation checklist remains incomplete until those gates pass.
- Roadmap Phase 10 lists only three parlay bullets; the feature specification
  requires attribution, counterfactuals, straight-position comparison, sensitivity,
  and reproducibility as well. Treat the feature spec as the acceptance authority;
  expand the Phase 10 work plan before implementing it.
- Canonical/API designs are conceptual, not executable schemas. ParlayEvaluation
  and exact event schemas remain to be defined in their implementation phases.
- Authentication provider/configuration, historical acquisition and licensing,
  production sizing, and advanced parlay/model thresholds remain open. None blocks
  workspace initialization. Human review is required before protected behavior,
  IAM/networking, licensing assumptions, or breaking contracts are implemented.
- The reference-patterns source documents are not present; their maintained
  adopted-patterns summary is available and authoritative for this repository.

No unresolved decision requires user input before the initial workspace increment.
Tool versions and formatting configuration are reversible implementation choices.

## Phase 1 increments

| Increment / intended commit | Objective and paths | Dependencies | Acceptance and validation |
| --- | --- | --- | --- |
| `docs: Record repository baseline and foundation plan` | Preserve supplied docs; add README, ignore rules, this review | None | Review staged diff and local document links |
| `chore: Initialize polyglot workspace tooling` | pnpm/Turbo/uv configs, lockfiles, scripts, tooling documentation | Baseline | Reproducible bootstrap; format/lint and workspace checks via scripts/validate |
| `feat(api): Add FastAPI application skeleton` | apps/api, health endpoint, Python quality checks | Workspace | Health endpoint offline tests, typecheck, package build |
| `feat(contracts): Generate OpenAPI TypeScript client` | contracts/openapi, libs/typescript/api-client, generation scripts | API | Repeatable generation, generated-drift check, client typecheck |
| `feat(dev): Add PostgreSQL and Floci environment` | Compose config, migration framework, local-up/local-down | API | Container readiness, migration round trip, local integration |
| `test(providers): Add local fixture and mock harness` | tests/fixtures/providers, mock server, integration tests | Local stack | Synthetic fixture HTTP integration without provider traffic |
| `feat(web): Initialize terminal application` | apps/web React/Vite shell | Client | Typecheck and production build |
| `feat(mobile): Initialize Expo application` | apps/mobile Expo shell | Client | Typecheck and Expo export; device validation reported separately |
| `feat(mcp): Initialize MCP server` | apps/mcp protocol shell | API/client | Protocol handshake smoke test and build; no speculative business tools |
| `feat(infra): Initialize credential-free CDK skeleton` | infra/cdk, scripts/synth | Workspace | Empty stack synthesizes without credentials or context lookups |
| `ci: Add foundation validation workflow` | .github/workflows, full scripts/validate | All preceding | Fresh-checkout validation, drift, quality, tests, integration, synth, security scan, build |

Introduce canonical root commands as their checks become real. Do not create
success-returning placeholders for unimplemented tests or services. Until phase
exit, scripts/validate must report its narrower coverage explicitly.

## Proposed Phase 1 tree

```text
README.md, AGENTS.md, CLAUDE.md
.gitignore, .editorconfig
package.json, pnpm-workspace.yaml, pnpm-lock.yaml, turbo.json
pyproject.toml, uv.lock, .python-version
apps/
  api/                 # FastAPI shell and migration framework
  web/                 # React/Vite shell
  mobile/              # Expo shell
  mcp/                 # MCP protocol adapter shell
libs/typescript/api-client/
contracts/openapi/
infra/cdk/             # synthesis only; no deployment resources yet
compose.yaml           # PostgreSQL, Floci, mock provider
tests/
  fixtures/providers/  # synthetic/sanitized fixtures plus metadata
  integration/
scripts/               # add wrappers with their implementations
.github/workflows/
docs/                  # existing design plus implementation records
```

Do not create workers, sport plugins, domain engines, future sport directories,
event consumers, or production infrastructure merely to populate the TDD tree.

## Progress and validation

Initial review complete. Implementation and validation results are recorded below
as increments land. Phase 1 is not yet complete.

Baseline validation: 27 Markdown files inspected, all 23 relative Markdown links
resolved. Git's initial whitespace check flagged the supplied Markdown hard
line breaks; .gitattributes permits Markdown end-of-line spaces, preserving the
source documents unchanged. The adjusted staged diff check passed.
