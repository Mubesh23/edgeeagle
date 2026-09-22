# Monorepo Engineering Guide

**Status:** Draft

## Repository model

One polyglot repository contains web, mobile, API, MCP, workers/jobs, sport plugins, contracts, infrastructure, tests, and docs. Deployment remains independent.

## Dependency direction

Applications depend on application/domain libraries. Domain logic does not depend on FastAPI, AWS SDKs, React, database clients, or provider SDKs. Infrastructure/provider adapters implement interfaces owned by the domain/application layer.

## TypeScript

Recommended package management: pnpm workspaces. Task orchestration/caching may use Turborepo.

## Python

Recommended package/workspace management: uv. Use Ruff, type checking, and pytest.

## Generated code

Generated clients/schemas must be declared in `AGENTS.md`, contain markers where feasible, and be validated by generated-drift checks. Fix the source schema/query, not generated output.

## Root commands

All common commands run from repository root through `scripts/` wrappers. Package-specific commands belong in package-level docs/AGENTS only when genuinely different.

## Agent-readiness

Root `AGENTS.md` should contain:

- purpose/owner
- root command table and safety properties
- generated/protected paths
- package map/dependency direction
- architecture entry points
- upstream/downstream systems
- data ownership
- invariants
- deployment restrictions
- definition of done
- known limitations

`CLAUDE.md` contains only `@AGENTS.md`.

## Git workflow and commit discipline

Incremental commits are part of the engineering contract for this repository, especially because substantial work may be performed by coding agents. A commit should represent one coherent, independently reviewable engineering step.

Do not defer all commits until the end of a phase or milestone. Do not combine unrelated concerns merely because they were implemented in the same session. When practical, foundational dependencies should be committed before their consumers.

Typical dependency-aware sequences include:

```text
contract/domain primitive
    -> commit
implementation
    -> commit
consumer integration
    -> commit
```

and:

```text
provider interface
    -> commit
fixtures and normalization models
    -> commit
provider adapter + tests
    -> commit
ingestion integration
    -> commit
```

A separate commit is not required for every individual file or tiny mechanical edit. The boundary is the smallest coherent change that can be understood, reviewed, and validated independently. Tests and documentation that are intrinsic to a feature normally belong in the same commit as that feature; a distinct architectural decision may justify a preceding ADR/documentation commit.

### Conventional Commits

All new commits use the **Conventional Commits** format:

```text
<type>(<optional-scope>): <description>
```

Preferred types:

| Type | Use |
|---|---|
| `feat` | New user-facing or system capability |
| `fix` | Bug fix |
| `docs` | Documentation-only change |
| `test` | Test-only change |
| `refactor` | Internal restructuring without behavior change |
| `perf` | Performance improvement |
| `build` | Build system or dependency-management change |
| `ci` | CI/CD workflow change |
| `chore` | Repository/tooling maintenance that fits no other type |
| `revert` | Revert of an earlier commit |

Use a short scope when it materially improves clarity, for example `api`, `web`, `mobile`, `mcp`, `data`, `providers`, `soccer`, `pricing`, `backtest`, `portfolio`, `infra`, or `docs`. Do not invent highly granular scopes simply to satisfy the syntax.

Examples:

```text
chore: initialize monorepo workspace
chore(python): initialize uv workspace
feat(api): add FastAPI health endpoint
feat(data): add canonical participant and event models
feat(providers): add Sportmonks adapter interface
test(providers): add Polymarket order-book fixtures
feat(dev): add Floci local AWS environment
feat(web): initialize terminal application
feat(mobile): initialize Expo application
feat(mcp): initialize MCP server
ci: add repository validation workflow
docs(adr): record local AWS emulation decision
```

Breaking changes must be intentional and explicit using `!` and/or a `BREAKING CHANGE:` footer. Contract-first evolution should normally make breaking changes uncommon.

### Before committing

For each coherent increment:

1. Review the complete diff.
2. Run the cheapest relevant validation first.
3. Run broader validation when the change crosses package or contract boundaries.
4. Regenerate generated artifacts when their sources changed.
5. Ensure tests needed to prove the increment are included.
6. Remove secrets, credentials, temporary diagnostics, local-machine artifacts, and unrelated edits.
7. Update docs/ADRs when commands, contracts, boundaries, invariants, or architectural decisions changed.
8. Commit only when the increment is reviewable and intentionally complete.

Validation should scale with scope:

```text
format/lint
    -> typecheck
    -> targeted unit tests
    -> package/integration tests
    -> scripts/validate when appropriate
```

A knowingly broken commit should be exceptional and explicitly justified as part of a controlled migration. Prefer maintaining a working or intentionally compatible repository between commits.

### Git safety

Do not force-push, rewrite published history, squash existing commits, rebase shared work, amend another contributor's commit, delete branches, or discard user-authored changes unless explicitly authorized. Do not push, tag, release, or deploy merely because local commits are allowed.

If unrelated changes already exist in the working tree, preserve them and isolate the current task rather than resetting them. Opportunistic cleanup should be left alone or committed separately only when necessary and within scope.

### Agent handoff

At the end of an implementation session, report the commits created using their short hash and Conventional Commit subject, together with the purpose of each commit, major files changed, validation performed, current working-tree status, uncommitted changes, unresolved risks, and the next recommended increment.

## Infrastructure rule

Agents/developers may run `cdk synth` locally. Production deployment is a separately authorized action. Stateful replacement/deletion, IAM broadening, and networking changes receive explicit human review.

## Definition of done for a normal change

- format/lint/typecheck pass
- unit tests pass
- relevant local integration tests pass
- generated output is current
- API/event compatibility passes where touched
- CDK synth passes where infra touched
- docs/ADRs updated when behavior/boundaries changed
- unrun validation is explicitly reported
