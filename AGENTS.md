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
The React/Vite web shell uses the generated API client for liveness; see
[`apps/web/README.md`](apps/web/README.md) for its local development commands.
The offline Expo mobile shell is included in root checks; its build exports
iOS/Android bundles, not native binaries. See [mobile commands](apps/mobile/README.md).
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

## Generated files

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

Generated paths must be documented with their source and regeneration command. Do not hand-edit generated OpenAPI clients or generated event/schema artifacts.

## Protected/high-risk areas

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
