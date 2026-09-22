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

| Increment / intended commit                            | Objective and paths                                               | Dependencies  | Acceptance and validation                                                                  |
| ------------------------------------------------------ | ----------------------------------------------------------------- | ------------- | ------------------------------------------------------------------------------------------ |
| `docs: Record repository baseline and foundation plan` | Preserve supplied docs; add README, ignore rules, this review     | None          | Review staged diff and local document links                                                |
| `chore: Initialize polyglot workspace tooling`         | pnpm/Turbo/uv configs, lockfiles, scripts, tooling documentation  | Baseline      | Reproducible bootstrap; format/lint and workspace checks via scripts/validate              |
| `feat(api): Add FastAPI application skeleton`          | apps/api, health endpoint, Python quality checks                  | Workspace     | Health endpoint offline tests, typecheck, package build                                    |
| `feat(contracts): Generate OpenAPI TypeScript client`  | contracts/openapi, libs/typescript/api-client, generation scripts | API           | Repeatable generation, generated-drift check, client typecheck                             |
| `feat(dev): Add PostgreSQL and Floci environment`      | Compose config, migration framework, local-up/local-down          | API           | Container readiness, migration round trip, local integration                               |
| `test(providers): Add local fixture and mock harness`  | tests/fixtures/providers, mock server, integration tests          | Local stack   | Synthetic fixture HTTP integration without provider traffic                                |
| `feat(web): Initialize terminal application`           | apps/web React/Vite shell                                         | Client        | Typecheck and production build                                                             |
| `feat(mobile): Initialize Expo application`            | apps/mobile Expo shell                                            | Client        | Typecheck and Expo export; device validation reported separately                           |
| `feat(mcp): Initialize MCP server`                     | apps/mcp protocol shell                                           | API/client    | Protocol handshake smoke test and build; no speculative business tools                     |
| `feat(infra): Initialize credential-free CDK skeleton` | infra/cdk, scripts/synth                                          | Workspace     | Empty stack synthesizes without credentials or context lookups                             |
| `ci: Add foundation validation workflow`               | .github/workflows, full scripts/validate                          | All preceding | Fresh-checkout validation, drift, quality, tests, integration, synth, security scan, build |

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

Workspace increment implemented: private pnpm 10.34.5 workspace, Turbo 2.11.3
task graph, Prettier 3.9.8, Python 3.11 virtual uv workspace, generated lockfiles,
and bootstrap/format-check/lint/validate scripts. No application packages yet.

Validation performed: dependency installation and lock generation; frozen/locked
scripts/bootstrap; Prettier formatting check; JavaScript and shell syntax checks;
workspace invariants and 25 relative documentation links; offline uv lock check;
Turbo task graph dry run. The combined scripts/validate passed. Sandbox runs
first hit Corepack/uv cache permissions and pnpm's noninteractive cache-directory
handling; approved runs with normal cache access succeeded. Dependency downloads
used public registries; no sports provider or AWS calls were made deliberately.
Turbo telemetry is disabled in the validation wrapper.

Not yet implemented or validated: API/web/mobile/MCP applications, application
typechecks/unit tests/builds, generated API/client contracts, PostgreSQL migrations,
Floci/mock integration, CDK synth, security scanning, and baseline CI. The next
increment is the FastAPI health-only skeleton and Python quality/test/build tools.

API increment implemented: installable apps/api uv member with a typed `/health`
liveness operation and `/openapi.json`. Root wrappers now include strict mypy,
Ruff, network-blocked pytest, and offline package builds. There is no database,
provider, authentication, risk, or execution behavior in this application shell.

API validation: scripts/bootstrap passed after regenerating uv.lock;
scripts/validate passed formatting, lint, typechecking (3 Python files), 2 API
tests with IP sockets disabled, lock freshness, Turbo graph parsing, and building
both sdist and wheel. Initial formatting/import configuration failures were fixed
before the successful run. Two upstream deprecation warnings remain: Starlette's
httpx test transport and its AnyIO BlockingPortal alias. They did not fail tests
and are not suppressed. No production runtime or cloud deployment was attempted.

Clean-snapshot verification: copied the staged repository files into a new
temporary directory without node_modules or .venv, then ran scripts/bootstrap
and scripts/validate successfully using existing package-manager caches. The
temporary location initially selected Node 18 through shell defaults; the checks
were repeated successfully with Node 20.20.1 explicitly selected. This proves
fresh local environment creation, not an empty-cache or container/CI run.

Created history so far: `d502954 docs: Record repository baseline and foundation plan`
and `26e43f5 chore: Initialize polyglot workspace tooling`. The API changes and this
validation record belong to `feat(api): Add FastAPI application skeleton`.

Next increment: persisted OpenAPI export, generated TypeScript API client, and
deterministic generated-drift checks. Remaining Phase 1 gates listed above still
apply, except the API shell and its Python quality/test/build checks are now done.

## OpenAPI and typed-client increment

The next coherent increment implements local FastAPI export to
`contracts/openapi/edgeeagle.json`, generated types under
`libs/typescript/api-client/src/generated/schema.ts`, and a maintained
openapi-fetch entry point in `@edgeeagle/api-client`. No new application routes,
domain behavior, or ADR decisions are introduced. Generation uses pinned
openapi-typescript and Prettier and rejects external references.

`scripts/generate-contracts` writes both artifacts. `scripts/check-generated`
recomputes them in memory and fails without repairing missing or stale files.
Root validation now includes drift checks and actual Turbo client tasks.
Bootstrap creates a local Corepack pnpm shim; root scripts expose its absolute
path to Turbo. Client types explicitly exclude ambient packages from ancestor
directories. These resolve issues discovered by exercising the first TS package.

Validation: bootstrap and full scripts/validate passed; strict mypy checked four
Python files, TypeScript checked both positive and negative contract examples,
two API tests passed, one generation regression test passed (repeatability,
missing output, independent JSON/TS drift, non-mutating comparison), and two
injected-fetch client tests passed. API sdist/wheel and client ESM/declarations
built. Existing two upstream Python deprecation warnings remain unsuppressed.

Released-contract compatibility, container integration, CDK synth, security scans,
CI, and web/mobile/MCP apps remain pending. No provider or production calls were
required. Next planned increment is local PostgreSQL/Floci and migrations.

Clean-snapshot check also passed: staged files copied to a new temporary
directory with no node_modules, .venv, or Turbo cache; scripts/bootstrap and
scripts/validate succeeded on Node 20.20.1 using existing download caches.
All client tasks executed before build-output reuse at the final build step.
This was local validation, not a CI or deployed-environment run.

## Local-services increment

Added Compose project edgeeagle-local with PostgreSQL 17.11-alpine3.23 and Floci
2.1.0, loopback-only ports, named persistent volumes, and health checks. Root
local-up/local-down/test-integration commands manage this stack; full validation
now includes it. Unit tests remain network-free and integration tests use only
explicit loopback endpoints. Migrations and provider mocks follow separately.

Docker Desktop was installed but stopped; it was started with approval. Image
downloads succeeded. The native Floci image uses its own healthcheck.sh and lacks
wget; startup testing exposed this distinction from the upstream JVM Dockerfile.
The corrected health check passed and persistent storage was enabled explicitly.

Validated Compose configuration, bootstrap/lock generation, format/lint, strict
Python checks, and two local smoke tests: PostgreSQL transaction and Floci S3
round trip. Smoke tests remove their own temporary resources. No paid provider
calls, production resources, IAM changes, or domain schemas are involved.
Full scripts/validate passed including the existing API/client/contract checks
and both local integration tests. Services are left healthy and running.

## Migration framework increment

Local services landed as `888de74 feat(dev): Add PostgreSQL and Floci environment`.
The next increment adds Alembic configuration, a revision template, and the empty
0001_foundation baseline under apps/api/migrations. scripts/migrate targets only
the local Compose database by default and does not run at API startup. No domain
tables or business API changes were introduced; autogeneration awaits Phase 2
metadata. Migration files are checkout assets, not packaged in the API wheel.

Validation passed: bootstrap with regenerated lockfile; Ruff and strict mypy
(9 files); full scripts/validate with 3 Python unit tests, the generation regression
test, existing client checks, and 3 local integration tests. Unchanged TypeScript
tasks used valid Turbo cache results in the final run. Migration tests verify
offline SQL, one head, repeat upgrade, committed state, downgrade, and reapplication
in a unique test database. Test resources were removed after use.

scripts/migrate applied the baseline to the development database. A real
scripts/local-down -> scripts/local-up -> scripts/migrate current cycle returned
0001_foundation (head), proving the database state survived container replacement.
Named volumes were retained, and PostgreSQL/Floci are healthy and running.

Remaining gates: provider fixture/mock server, client applications, CDK synth,
released-contract compatibility, security scanning, and CI. No provider credentials,
paid API calls, production deployment, or new ADR decision was required. The
next increment is the provider fixture/mock harness. Existing two upstream Python
deprecation warnings remain unsuppressed.

## Provider fixture/mock increment

Added a deliberately limited synthetic The Odds API-shaped soccer fixture with
explicit provenance and separate data-source/bookmaker identity. The stdlib-only
mock serves success, empty, rate-limit, server-error, and malformed responses;
scenarios are per-request and never call upstream providers. This is a testing
harness, not a provider adapter or evidence of live contract compatibility.

Compose now builds the mock from a restricted test-only context and runs it as
a non-root user with a read-only filesystem, published on loopback port 9080.
local-up rebuilds the image to pick up fixture edits. Root unit tests include
network-disabled routing tests; integration tests exercise real loopback HTTP.
No application contract, domain model, dependencies, or ADR decisions changed.

Validation passed: 13 targeted mock unit tests, 9 local integration tests, and
full scripts/validate (16 Python unit tests, 1 generation regression test,
generated-artifact freshness, formatting, Ruff, strict mypy over 14 files,
lock freshness, and builds). Unchanged TypeScript typecheck, two client tests,
and client build reused valid Turbo cache results. An initial pytest import-path
failure was corrected by explicitly including the repository root in pythonpath.
The two existing upstream Python deprecation warnings remain unsuppressed.

PostgreSQL, Floci, and the provider mock are healthy and left running. No paid
provider calls, credentials, production deployment, or licensing assumptions were
required. Live provider contract tests, released-contract compatibility checks,
security scans, CDK synth, client applications, and CI remain unimplemented.
The next planned increment is the React/Vite web shell using the generated client.

## Web foundation increment

Added apps/web with React, TypeScript, Vite, TanStack Query, and the generated
API client. A neutral research shell displays loading, process liveness, and
failure/retry states. It contains no market fixtures, pricing logic, authentication,
or trading capabilities. Router/Table packages remain deferred until used.
This follows the existing TDD; no new architectural decision or ADR is needed.

Development uses a loopback-only Vite proxy from /api to the local FastAPI
process. Static hosting must supply that routing separately; no production
deployment or backend CORS change was made. Fetching consumes cancellation,
has a five-second timeout, and requires explicit user retries.

Validation passed: frozen bootstrap after lock generation, web ESLint/strict
TypeScript, six injected-transport component tests, and full scripts/validate.
That run also passed 16 Python unit tests, the generated-contract regression,
9 local integration tests, generated drift, formatting, lock freshness, and
API/web builds. Existing client checks used valid Turbo cache results.
A real Vite server served HTML and proxied /api/health to FastAPI, returning
200 with status ok. Both temporary development servers were then stopped;
PostgreSQL, Floci, and provider mocks remain running.

No real-browser rendering/E2E or fresh-checkout validation was performed in this
increment. No provider calls or AWS credentials were used. npm reported ESLint 9
and transitive whatwg-encoding deprecations; pnpm blocked esbuild's install script,
but its optional platform binary successfully ran the local build and tests.
Existing Python deprecation warnings remain. CI/security scans and mobile/MCP/CDK
shells remain pending. Next recommended increment: the Expo mobile foundation.

## Mobile foundation increment

Added an offline Expo Router native-stack shell under apps/mobile, following
ADR-007 and the TDD. It uses selectable, font-scalable native text and safe-area
spacing, with no network calls, credentials, product tabs, or business logic.
The generated client and Query layer await an actual mobile data workflow.
No new architecture decision or production infrastructure was introduced.

Pinned SDK 56 to match the existing Node 20.20.1 environment, with its React
19.2.3/React Native 0.85.3/TypeScript 6.0.3 compatibility set. Root Node engines
now reflect the native runtime tooling requirements. Expo's public dependency
check passed after resolving initially mismatched auto-installed native peers
and the TypeScript recommendation. These pins remain local to mobile.

Validation passed: lock generation and frozen bootstrap, mobile ESLint and
strict TypeScript, one jest-expo native component test, offline iOS and Android
Metro/Hermes exports, and full scripts/validate. The full run also executed six
web tests, two client tests, the generation regression, 16 Python unit tests,
9 local integration tests, generated drift, formatting, and all builds.
Build outputs were reused at the final build step after running earlier in the
same validation. Dependency deprecations and the two existing Python warnings
remain unsuppressed.

Expo Go mode started without credentials; an iOS manifest was served. The smoke
check found localhost binding on IPv6 while Expo advertised IPv4. The development
command now uses IPv4-first DNS resolution; the advertised 127.0.0.1 endpoint
then returned packager-status:running. The temporary Metro server was stopped.
PostgreSQL, Floci, and the provider mock remain running.

The mobile-design skill's heuristic audit ran and returned FAIL: it mistook the
test viewport width 390 for a 39px touch target. There are no interactive controls
in this increment. Its additional theme/typography/safe-area warnings were reviewed;
the screen uses RN's default font scaling, native safe-area insets, and the PRD's
dark analytical palette. This is not an accessibility certification or audit pass.

No simulator/device runtime, screen-reader, native binary build, signing, or
fresh-checkout check was performed. simctl is unavailable on this machine.
Native bundles do not prove native runtime behavior. EAS, production identifiers,
auth, push, and provider calls remain absent. Next recommended increment: MCP
server foundation over the existing authoritative API boundary.

## MCP protocol foundation increment

Added apps/mcp with the official TypeScript MCP SDK, local stdio transport,
initialization/ping, and an explicitly empty tool list. Calls to unavailable
tools fail with InvalidParams. No speculative research tools, domain logic,
API calls, credentials, HTTP listeners, or client installations were introduced.
The API-client dependency will be added when a backend capability is exposed.
Stdio is a local foundation transport, not a production deployment/auth decision.

Validation passed: regenerated lockfile and frozen bootstrap, package ESLint,
strict TypeScript/build, and two real subprocess protocol tests. An official
SDK client exercises handshake, ping, discovery, unavailable-tool rejection, and
continued liveness; a separate process verifies clean EOF exit and quiet stdout.
The initial lint failure for an undeclared URL global was fixed with a Node import.

Full scripts/validate passed: generated drift, formatting, lint/typechecks,
16 Python unit tests, one generation regression, two MCP tests, one mobile
component test, 9 local integration tests, and all builds. Unchanged web/client
checks used valid Turbo cache results. Mobile bundles/tests reran after lockfile
peer resolution changed Node types to the pinned Node 20 types. Final build steps
reused outputs already verified by the same run. Existing dependency/Python
deprecation warnings remain.

No desktop-agent application integration, remote/authenticated MCP transport,
fresh-checkout check, or production deployment was performed. Protocol tests
close their child processes; local Docker services remain healthy and running.
No new ADR is needed for this scoped implementation of the existing plan.
Next recommended increment: an empty CDK foundation with credential-free synth;
CI, security scanning, and released-contract compatibility remain outstanding.
