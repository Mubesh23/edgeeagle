# Foundation CI

`.github/workflows/validate.yml` runs on pull requests, pushes to the documented
foundation/feature/fix/CI branches and main/master, and manual dispatch. It uses
an ephemeral Ubuntu 24.04 runner, Node 22, Python 3.11, uv 0.7.3, Corepack 0.34.6,
and the repository-pinned pnpm. Runtime patch releases follow their setup actions;
project dependencies remain frozen in the lockfiles.

Actions are pinned to verified commit SHAs. The job has read-only repository
permissions, no persisted checkout token, no secrets or OIDC, no deployment,
no provider calls, and no shared build/dependency cache. It runs the same
`scripts/bootstrap` and `scripts/validate` commands used locally. Docker starts
only PostgreSQL, Floci, and the synthetic provider mock. Cleanup runs even after
failure and does not delete volumes. A 30-minute timeout and concurrency
cancellation limit redundant runs.

Registry/image downloads require public network access. GitHub-hosted runner
minutes may count toward the repository owner's plan; no workflow is triggered
or pushed by local development. Repository branch protection is not configured
by this change.

The workflow policy test runs in `scripts/test-unit`. It parses YAML and checks
the action pins, triggers, permissions, command ordering, and cleanup. It is not
a substitute for a real GitHub Actions run. Local validation does not prove
Linux runner compatibility. OpenAPI compatibility is checked against a frozen
pre-release foundation snapshot, not a released API. Security scanning remains
pending until its root gate is implemented.
