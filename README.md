# EdgeEagle

Multi-sport quantitative sports-market research, backtesting, paper trading,
and portfolio management. **Price, not picks.** Soccer is the first modeled sport;
real-money execution and live revaluation are later capabilities.

Start with the [documentation index](docs/README.md),
[PRD](docs/product/PRD.md), [TDD](docs/architecture/TDD.md), and
[repository instructions](AGENTS.md).

Roadmap Phase 1 foundation is implemented and has passed local fresh-checkout
bootstrap/validation without AWS credentials or paid provider calls. Hosted CI
and native-device validation are not yet demonstrated. The
[readiness review and incremental plan](docs/development/foundation-readiness.md)
records the initial state, scope discrepancies, acceptance gates, and progress.
Commands described in the architecture are targets until explicitly implemented.

For implemented commands and prerequisites, see
[workspace tooling](docs/development/workspace-tooling.md). Start with
`scripts/bootstrap`, then `scripts/validate`.

The first application is the [FastAPI health-only shell](apps/api/README.md).
Its [OpenAPI snapshot and typed client](contracts/README.md) are generated locally
with `scripts/generate-contracts` and verified by `scripts/check-generated`.

Full validation now needs Docker with Compose v2.15+ and starts local PostgreSQL
and Floci. `scripts/local-down` stops the stack while preserving its data volumes.
See [local development](docs/development/local-development-testing.md).

The [synthetic provider mock](tests/mock_providers/README.md) is also started and
tested by those commands, without API keys or provider traffic.

The [web foundation](apps/web/README.md) now provides a local React/Vite shell
with a generated-client API liveness check.

The [mobile foundation](apps/mobile/README.md) provides an offline Expo Router
shell and credential-free iOS/Android bundle exports.

The [MCP foundation](apps/mcp/README.md) provides a local stdio protocol shell
with an empty tool list; business tools remain deferred.

The [CDK foundation](infra/cdk/README.md) provides credential-free synthesis of
an empty stack. It creates no AWS resources and is not deployable yet.

The [CI workflow](docs/development/ci.md) runs the root validation commands.
Validation includes frozen [OpenAPI compatibility](contracts/baselines/README.md)
and [dependency security scans](docs/development/security-scanning.md); the latter
require access to public advisory services, not paid providers.
