# EdgeEagle

Multi-sport quantitative sports-market research, backtesting, paper trading,
and portfolio management. **Price, not picks.** Soccer is the first modeled sport;
real-money execution and live revaluation are later capabilities.

Start with the [documentation index](docs/README.md),
[PRD](docs/product/PRD.md), [TDD](docs/architecture/TDD.md), and
[repository instructions](AGENTS.md).

Implementation is beginning with roadmap Phase 1. The
[readiness review and incremental plan](docs/development/foundation-readiness.md)
records the initial state, scope discrepancies, acceptance gates, and progress.
Commands described in the architecture are targets until explicitly implemented.

For implemented commands and prerequisites, see
[workspace tooling](docs/development/workspace-tooling.md). Start with
`scripts/bootstrap`, then `scripts/validate`.

The first application is the [FastAPI health-only shell](apps/api/README.md).
Its [OpenAPI snapshot and typed client](contracts/README.md) are generated locally
with `scripts/generate-contracts` and verified by `scripts/check-generated`.
