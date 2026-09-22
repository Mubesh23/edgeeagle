# CDK foundation

This TypeScript workspace implements the existing TDD's CDK choice, with one
environment-agnostic, resource-free stack. No account, region, lookups, IAM,
networking, queues, storage, or deployment pipeline is configured.

From the repository root, after `scripts/bootstrap`:

```sh
scripts/synth
corepack pnpm --filter @edgeeagle/infra lint
corepack pnpm --filter @edgeeagle/infra typecheck
corepack pnpm --filter @edgeeagle/infra build
corepack pnpm --filter @edgeeagle/infra test
```

Tests consume compiled output, so build before running package tests directly.
Root unit tests handle that dependency through Turbo. Root validation includes
synthesis; standalone synthesis does not require Docker, Floci, AWS credentials,
or a bootstrapped AWS environment. Dependency installation needs package registries.

The wrapper compiles the app, then launches the pinned CDK CLI with an allowlisted
environment: PATH, empty AWS config/credentials files, and metadata credentials
disabled. It does not inherit profiles, web identity, container credentials,
endpoint overrides, or CDK account/region variables. Lookups, telemetry, notices,
version reporting, and path/asset metadata are disabled. There is no deploy command.

The synthesized template is `{}`. CDK warns that CloudFormation requires a
non-empty Resources section: this is expected, and means the scaffold is **not
deployable**. Synth success is not deployment validation. CDK also reports
unconfigured feature flags; deployment defaults must be reviewed when actual
resources are introduced, not selected speculatively here.

The default synthesizer registers the template itself as file-asset metadata.
Tests allow only that template, with no application assets, Docker images,
resources, or missing context. Bootstrap-version rules are disabled for this
resource-free scaffold; revisit that setting before adding deployable resources.
No assets are uploaded and no resources are created by these commands.

Generated `dist/` comes from `src/` and `tsconfig.json` via `scripts/build`.
Generated `cdk.out/` comes from `src/` and `cdk.json` via `scripts/synth`.
Both are ignored and must not be hand-edited or committed. Production resources,
IAM/networking, deployment configuration, and stateful changes require the
repository's documented review gates.
