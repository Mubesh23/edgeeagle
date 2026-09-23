# Workspace tooling

Phase 1 starts with a private pnpm workspace, Turborepo task graph, and a virtual
uv workspace. apps/api is the first Python member; it supplies a health-only
FastAPI application. No future domain package is created merely to fill the
planned directory tree. Python members are registered as they land.

Phase 2 adds [the pure Python domain library](../../libs/python/domain/README.md)
with independent source/venue primitives. Root Python formatting, lint, strict
typing, network-blocked unit tests, and offline sdist/wheel builds include it.
It has no runtime dependencies. Source/venue and sports/event database entities
are maintained by Alembic, not implicit dependencies of the domain package.
The [persistence library](../../libs/python/persistence/README.md) implements
source/venue and sports/event repository ports with caller-owned transactions. Root checks and
offline package builds include it; real transaction tests use disposable local
PostgreSQL databases. Mapping-history schema now exists under
[ADR-014](../adr/ADR-014-provider-mapping-storage.md), with a transactional mapping
repository and local concurrent-writer/replay/snapshot tests. API/ingestion wiring
and pinned historical datasets remain later increments.

## Prerequisites and bootstrap

Use a Node version matching the root engine range (prefer a supported LTS),
Corepack, Python 3.11, and uv >=0.7.3.
pnpm enforces the declared Node engine range during installation. If a shell or
version manager selects an older Node outside the original checkout, select a
supported runtime before bootstrap; an engine warning must not be ignored.
The initial workspace was exercised with Node 20.20.1 and Python 3.11.5; this is
local compatibility evidence, not a production runtime policy. pnpm is pinned
in package.json and invoked through Corepack without a global pnpm installation.
Bootstrap also creates a pnpm shim in ignored `node_modules/.bin` so Turbo can
resolve the package manager when executing workspace tasks. No global shim is installed.

Run `scripts/bootstrap` from the checkout. Initial installation requires access
to public package registries and may populate package-manager caches. No AWS
credentials or provider API calls are used. Subsequent quality checks use locally
installed dependencies. Bootstrap does not start containers. Full validation now
starts PostgreSQL and Floci through `scripts/test-integration` and requires a
running Docker daemon with Compose v2.15+. Services remain running afterward;
use `scripts/local-down` to stop them while retaining their named data volumes.

## Implemented commands

| Command                      | Current coverage                                                                       |
| ---------------------------- | -------------------------------------------------------------------------------------- |
| `scripts/bootstrap`          | Frozen pnpm install and locked uv workspace sync                                       |
| `scripts/format-check`       | Prettier and Ruff formatting                                                           |
| `scripts/lint`               | JavaScript/shell syntax, workspace invariants, Markdown links, Ruff                    |
| `scripts/typecheck`          | Strict mypy and TypeScript client checks                                               |
| `scripts/test-unit`          | API tests with IP sockets blocked, generation regressions, injected-fetch client tests |
| `scripts/build`              | Offline API sdist/wheel and TypeScript client build                                    |
| `scripts/generate-contracts` | Local OpenAPI export and generated TypeScript types                                    |
| `scripts/check-generated`    | Non-mutating comparison of generated artifacts with source                             |
| `scripts/check-contracts`    | OpenAPI compatibility against the frozen pre-release snapshot                          |
| `scripts/security-scan`      | npm and Python dependency advisory checks, including development tools                 |
| `scripts/synth`              | Credential-free, lookup-disabled synthesis of the resource-free CDK shell              |
| `scripts/validate`           | All current checks, offline uv lock freshness, Turbo graph parsing                     |

Use `corepack pnpm run format` to format maintained files. The supplied design
documents are deliberately excluded from mechanical formatting to preserve the
baseline. Markdown hard breaks are permitted by .gitattributes.

Use `uv run --locked --offline --all-packages ruff format apps/api` for Python
formatting. The build wrapper expects `scripts/bootstrap` to have installed the
locked build backend first.

Validation now also covers API Ruff format/lint, strict mypy, network-blocked
pytest, and an offline sdist/wheel build. Use `scripts/typecheck`,
`scripts/test-unit`, and `scripts/build` to run those gates separately.
`scripts/format-check` and `scripts/lint` include Python checks as well.
Generated drift checks now run first in validation. TypeScript build/typecheck/test
tasks run through Turbo; client tests depend on their build. Python arguments
passed to `scripts/test-unit` apply only to pytest. No client tests use real HTTP.
PostgreSQL and Floci smoke tests now run at the end of validation. See
[local development](local-development-testing.md) for ports and lifecycle.
`scripts/migrate` applies local Alembic migrations, now including independent
source/venue tables, capability sets, and the sports/event hierarchy with composite
foreign keys. See [migration scope and safety](../../apps/api/migrations/README.md).
Migration offline-SQL tests run with unit tests and isolated-database round trips
run with integration tests. Neither bootstrap nor API startup migrates a database.
Provider fixture routing tests now run with unit tests, and real loopback HTTP
mock tests run with integration tests. local-up builds the small fixture image
from a restricted Docker context; no Python package installation is needed inside it.
The React/Vite web shell now consumes the generated client for API liveness.
Root checks include web ESLint, strict TypeScript, injected-transport component
tests, and the static Vite build. See [web commands](../../apps/web/README.md).
The Expo mobile shell adds ESLint, TypeScript, a native component test, and
offline iOS/Android bundle exports to the same commands. These exports are not
native binary builds. See [mobile commands](../../apps/mobile/README.md).
The stdio MCP shell adds ESLint, TypeScript, build, and subprocess protocol tests.
See [MCP commands](../../apps/mcp/README.md); its tool list is intentionally empty.
The CDK shell adds ESLint, TypeScript, build, and resource/lookup assertions.
`scripts/synth` runs independently of Docker and is included in `scripts/validate`.
It clears inherited credentials and disables lookups, telemetry, and metadata
credentials. See [CDK commands](../../infra/cdk/README.md) for expected warnings.
`scripts/check-contracts` uses a digest-pinned, network-disabled Docker comparator
against a frozen pre-release snapshot. Actual comparator regression cases run in
local integration tests. No released API or event baseline exists yet.
`scripts/security-scan` audits npm/Python dependencies, including development
tools, and fails on findings or unavailable advisory services. It runs without
Turbo caching as part of validation and requires public registry/advisory network
access. See [scan scope](security-scanning.md); this is not a comprehensive
application security audit. Phase 1 exit still requires fresh-checkout evidence.

The [foundation CI workflow](ci.md) invokes bootstrap and validation on a fresh
GitHub-hosted Linux runner without provider/AWS credentials. Its YAML policy test
runs with unit tests. A locally passing command is not a hosted CI run.

## Dependency and generated-file policy

TypeScript packages use `workspace:*` for internal dependencies. Python members
share uv.lock; uv is the Python dependency manager, not pnpm. Applications depend
inward on domain/application libraries; domain code never imports infrastructure.

pnpm-lock.yaml comes from package.json and pnpm-workspace.yaml; regenerate with
`corepack pnpm install --lockfile-only`. uv.lock comes from pyproject.toml and
member manifests; regenerate with `uv lock`. Review dependency changes before
committing. Do not hand-edit either lockfile. API/client generated paths and
commands are documented in [contracts](../../contracts/README.md) and AGENTS.md.

Tool configuration references: [pnpm workspaces](https://pnpm.io/workspaces),
[uv workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/), and
[Turborepo configuration](https://turborepo.com/docs/reference/configuration).
