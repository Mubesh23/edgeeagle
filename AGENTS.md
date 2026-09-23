# AGENTS.md

## Purpose

This repository contains the Multi-Sport Quantitative Betting & Trading Platform: web, mobile, API, MCP, data ingestion, modeling/backtesting, portfolio/risk, infrastructure, and documentation.

Read `docs/README.md`, `docs/product/PRD.md`, and `docs/architecture/TDD.md` before making architectural changes.

## Commands

Implementation status: workspace/API increments implement `bootstrap`,
`format-check`, `lint`, `typecheck`, `test-unit`, `build`, and `validate`.
`generate-contracts` and `check-generated` now export and verify local API artifacts.
`local-up`, `local-down`, and `test-integration` now manage/test PostgreSQL and
Floci. `validate` starts these local services and leaves them running; named data
volumes survive `local-down`. `scripts/migrate` manages the local Alembic history.
The synthetic provider mock now runs with local-up and is covered by unit and
HTTP integration tests; real provider adapters/contract tests are not implemented.
Migration `0002_source_venue` adds source/venue tables and capability sets; see
[migration scope](apps/api/migrations/README.md). Validation migrates disposable
test databases only, not the developer's application database.
Migration `0003_sports_events` adds the sports/event hierarchy and cross-record
foreign keys. Source/venue and sports/event transactional adapters now live in
[Python persistence](libs/python/persistence/README.md). Migration
`0004_mapping_history` adds append-only mapping storage. The mapping repository
supports compare-and-append, exact replay, and availability-based resolution;
ingestion/API wiring and pinned historical datasets remain deferred.
The persistence package also implements immutable raw S3 capture storage with
conditional writes and integrity-checked reads; see
[ADR-015](docs/adr/ADR-015-raw-payload-storage.md). Floci tests use disposable
buckets only; the storage adapter introduces no production bucket or orchestration.
The [ingestion library](libs/python/ingestion/README.md) composes bounded local-file
acquisition with raw retention. A versioned fixture-only event adapter now produces
canonical candidates using explicit bindings; see
[ADR-017](docs/adr/ADR-017-synthetic-event-normalization.md). It does not write
canonical records, publish events, or replace production mapping history.
The separate acceptance repository persists canonical candidates and immutable
receipts. Its publication-aware `accept_with_notification` method now also saves
an immutable outbox intent atomically; legacy `accept` remains persistence-only.
Delivery coordination now supports database-timed leases, fenced acknowledgements,
and scheduled retries in a separate operational table. A bounded transport-neutral
dispatcher now commits claims before sending and completes them in a new transaction;
the EventBridge adapter now verifies its explicit destination and per-entry broker
acceptance, with local Floci tests. A transactional verification consumer now
deduplicates accepted notifications in PostgreSQL and commits before queue deletion.
SQS routing, retries, processing-DLQ redrive, and queue-depth probes now have local
tests. EventBridge delivery-DLQ forwarding is a documented Floci 2.1.0 gap with a
strict expected-failure probe; no production permission enforcement is claimed. See
[ADR-023](docs/adr/ADR-023-event-acceptance-consumer.md),
[ADR-022](docs/adr/ADR-022-eventbridge-outbox-publisher.md),
[ADR-021](docs/adr/ADR-021-outbox-dispatch-boundary.md),
[ADR-019](docs/adr/ADR-019-event-outbox.md) and
[ADR-020](docs/adr/ADR-020-outbox-delivery-leases.md).
The API now exposes current-state event list/detail contracts, with explicit local
PostgreSQL composition, bounded ID pagination, and read-only request transactions.
The default credential-free app returns 503 for unconfigured event reads; see
[API setup](apps/api/README.md) and [ADR-024](docs/adr/ADR-024-event-read-api.md).
The React/Vite web shell uses the generated API client for liveness; see
[`apps/web/README.md`](apps/web/README.md) for its local development commands.
The offline Expo mobile shell is included in root checks; its build exports
iOS/Android bundles, not native binaries. See [mobile commands](apps/mobile/README.md).
The local stdio MCP shell supports protocol discovery with no business tools;
see [MCP commands](apps/mcp/README.md).
The resource-free CDK shell is included in root checks; `scripts/synth` runs
without AWS credentials or Docker. See [CDK commands](infra/cdk/README.md).
The [foundation CI workflow](docs/development/ci.md) runs bootstrap/validate on
GitHub-hosted Linux with no provider or AWS credentials; no deployment is defined.
`scripts/check-contracts` compares OpenAPI with the frozen pre-release foundation
checkpoint using a pinned, network-disabled Docker comparator. See
[baseline policy](contracts/baselines/README.md).
`scripts/security-scan` audits locked npm/Python dependencies using public
advisory services and runs in `validate`; see [scan scope](docs/development/security-scanning.md).
The table below describes the target
command set; unimplemented commands are not yet available. See
[`docs/development/workspace-tooling.md`](docs/development/workspace-tooling.md)
for current validation coverage and prerequisites.

All standard commands run from repository root.

| Command | Purpose | Credentials | External paid APIs | Deployed env |
|---|---|---|---|---|
| `scripts/bootstrap` | Install/generate local dependencies | No | No | No |
| `scripts/local-up` | Start PostgreSQL, Floci, mock providers | No | No | No |
| `scripts/test-unit` | Fast tests | No | No | No |
| `scripts/test-integration` | Local integration tests | No | No | No |
| `scripts/test-provider-contracts` | Explicit provider contract checks | Provider free/demo keys may be required | Must stay within configured budget | No |
| `scripts/validate` | Everything required before review | No for normal path | No | No |
| `scripts/synth` | CDK synth | No | No | No |

## Core invariants

- Provider-specific schemas stop at adapters.
- `DataSource` and `Venue` are different domain concepts.
- BFF owns no authoritative business data.
- Model -> pricing -> EV -> strategy -> risk logic is deterministic.
- Backtests may use only data whose `available_at` is <= simulated decision time.
- Queue/event handlers are idempotent and assume at-least-once delivery.
- Every queue has a DLQ and monitoring.
- Normal local/CI testing must not require paid provider calls or AWS credentials.
- Real-money execution, when introduced, must pass through risk and explicit confirmation.

## Git workflow

Incremental Git history is required. Work in small, coherent, reviewable increments and commit each completed increment before moving to the next independently reviewable unit of work. Do not accumulate an entire milestone or multiple unrelated concerns into one final commit.

Use **Conventional Commits** for all new commits:

```text
<type>(<optional-scope>): <description>
```

Common types include `feat`, `fix`, `docs`, `test`, `refactor`, `perf`, `build`, `ci`, `chore`, and `revert`. Use `!` and/or a `BREAKING CHANGE:` footer only for intentionally breaking changes.

Examples:

```text
chore: initialize monorepo workspace
feat(api): add FastAPI application skeleton
feat(data): add canonical event model
test(providers): add Kalshi fixture coverage
feat(dev): add Floci local AWS environment
ci: add repository validation workflow
docs(adr): record provider and venue strategy
```

Before each commit:

- review the diff
- run the cheapest relevant validation for the changed scope
- ensure generated artifacts are current where applicable
- ensure no secrets, credentials, temporary files, or unrelated changes are included
- update documentation when the change alters a command, contract, invariant, boundary, or architecture decision

Preserve dependency order between commits where practical. Do not mix unrelated features, cleanup, refactors, or infrastructure changes in one commit. Do not rewrite published/shared history, force-push, squash existing commits, or discard user-authored changes unless explicitly authorized.

The final handoff for an implementation session must report the commits created, validation performed, current working-tree status, and any uncommitted changes.

## Package boundaries

- `libs/python/ingestion` owns offline acquisition orchestration and its importer
  port, depending inward on domain. Its local-file adapter does not parse payloads.

- `libs/python/domain` is the pure Python domain library. Applications may depend
  inward on it; it must not import API, database, AWS, or provider SDK code.
- `libs/python/persistence` implements inward-owned domain repository ports using
  caller-owned PostgreSQL transactions and the raw storage port using a
  caller-supplied S3 client. Its EventBridge adapter implements ingestion's outbox
  publisher port using a caller-supplied client. Domain code must not import persistence.

## Generated files

- Root `dist/` contains ignored Python API/domain/persistence/ingestion sdist and wheel outputs from
  their member manifests and source packages; regenerate with `scripts/build`.

- `pnpm-lock.yaml`: source is root/member package manifests and
  `pnpm-workspace.yaml`; regenerate with `corepack pnpm install --lockfile-only`.
- `uv.lock`: source is root/member `pyproject.toml`; regenerate with `uv lock`.
- `contracts/openapi/edgeeagle.json` and
  `libs/typescript/api-client/src/generated/schema.ts`: source is FastAPI routes
  and response models in `apps/api/src/edgeeagle_api`; regenerate with
  `scripts/generate-contracts`. `scripts/check-generated` fails on missing/stale
  artifacts without modifying files. See `contracts/README.md`.
- `libs/typescript/api-client/dist/`: ignored TypeScript build output from the
  client sources; regenerate with `scripts/build`.
- `apps/web/dist/`: ignored static output from apps/web source and Vite config;
  regenerate with `scripts/build`.
- `apps/mobile/dist/`: ignored Expo iOS/Android bundles/assets/metadata from
  app/, src/, app.json, and dependencies; regenerate with `scripts/build`.
- `apps/mobile/.expo/`: ignored local Expo state, regenerated by Expo start/export.
- `apps/mcp/dist/`: ignored JavaScript output from apps/mcp/src and tsconfig.json;
  regenerate with `scripts/build`.
- `infra/cdk/dist/`: ignored JavaScript output from infra/cdk/src and tsconfig.json;
  regenerate with `scripts/build`.
- `infra/cdk/cdk.out/`: ignored cloud assembly from infra/cdk/src and cdk.json;
  regenerate with `scripts/synth`.
- `patches/query-string@7.1.3.patch`: generated package compatibility patch; its
  source, pnpm regeneration commands, and removal gates are in [patch policy](patches/README.md).

Generated paths must be documented with their source and regeneration command. Do not hand-edit generated OpenAPI clients or generated event/schema artifacts.

## Protected/high-risk areas

Compatibility snapshots in `contracts/baselines/` are immutable captured artifacts;
their provenance and capture command are documented there. Changes require human
review and are not part of normal contract regeneration.

Human review is mandatory for:

- execution/risk behavior
- authentication/authorization
- provider licensing assumptions
- stateful infrastructure replacement/deletion
- IAM/networking changes
- breaking API/event/schema changes

## Infrastructure

Use Floci for local AWS-shaped integration tests. `cdk synth` is the default infrastructure validation. Do not autonomously deploy production resources.

## Documentation

Architecture decisions require an ADR. Update docs when commands, contracts, boundaries, providers, or validation behavior changes. Vendor pricing/quotas belong in `docs/data/provider-evaluation.md` with a verification date.
