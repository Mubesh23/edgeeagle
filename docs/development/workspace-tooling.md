# Workspace tooling

Phase 1 starts with a private pnpm workspace, Turborepo task graph, and a virtual
uv workspace. No application or future domain package is created merely to fill
the planned directory tree. Python members will be registered as they land.

## Prerequisites and bootstrap

Use Node >=20.19 (prefer a supported LTS), Corepack, Python 3.11, and uv >=0.7.3.
The initial workspace was exercised with Node 20.20.1 and Python 3.11.5; this is
local compatibility evidence, not a production runtime policy. pnpm is pinned
in package.json and invoked through Corepack without a global pnpm installation.

Run `scripts/bootstrap` from the checkout. Initial installation requires access
to public package registries and may populate package-manager caches. No AWS
credentials or provider API calls are used. Subsequent quality checks use locally
installed dependencies. Neither bootstrap nor validation starts containers.

## Implemented commands

| Command                | Current coverage                                                            |
| ---------------------- | --------------------------------------------------------------------------- |
| `scripts/bootstrap`    | Frozen pnpm install and locked uv workspace sync                            |
| `scripts/format-check` | Prettier checks tooling and new documentation                               |
| `scripts/lint`         | JavaScript syntax, workspace invariants, local Markdown links, shell syntax |
| `scripts/validate`     | All current checks, offline uv lock freshness, Turbo graph parsing          |

Use `corepack pnpm run format` to format maintained files. The supplied design
documents are deliberately excluded from mechanical formatting to preserve the
baseline. Markdown hard breaks are permitted by .gitattributes.

Validation currently covers workspace tooling only. There are no application
tests, application typechecks/builds, generated contracts, integration checks,
security scans, or CDK synth yet. Those are missing checks, not passes. Add root
wrappers together with their real implementations. Phase 1 exit requires the
full roadmap gate, not merely this initial scripts/validate result.

## Dependency and generated-file policy

TypeScript packages use `workspace:*` for internal dependencies. Python members
share uv.lock; uv is the Python dependency manager, not pnpm. Applications depend
inward on domain/application libraries; domain code never imports infrastructure.

pnpm-lock.yaml comes from package.json and pnpm-workspace.yaml; regenerate with
`corepack pnpm install --lockfile-only`. uv.lock comes from pyproject.toml and
member manifests; regenerate with `uv lock`. Review dependency changes before
committing. Do not hand-edit either lockfile. API/client generated paths will be
declared when their generator lands.

Tool configuration references: [pnpm workspaces](https://pnpm.io/workspaces),
[uv workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/), and
[Turborepo configuration](https://turborepo.com/docs/reference/configuration).
