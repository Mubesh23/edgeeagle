# API contracts

FastAPI route/response definitions in `apps/api/src/edgeeagle_api` are authoritative.
`scripts/generate-contracts` imports the application locally and generates:

- `contracts/openapi/edgeeagle.json`: deterministic OpenAPI snapshot.
- `libs/typescript/api-client/src/generated/schema.ts`: generated TypeScript
  paths, operations, and components using pinned openapi-typescript.

Do not edit these outputs. Change the backend definitions, run
`scripts/generate-contracts`, review both outputs, and commit them together.
JSON object keys are sorted at export; pinned Prettier formats both outputs.
Generation does not start a server or fetch a schema. External `$ref` values
are rejected so references cannot introduce network retrieval.

`scripts/check-generated` regenerates both outputs in memory and compares their
bytes with the files on disk. Missing or changed files fail with a regeneration
instruction. The check never repairs files, and works before an initial commit;
it does not rely on `git diff`. `scripts/validate` runs it before other checks.

Bootstrap installs dependencies but does not regenerate contracts, ensuring stale
artifacts remain detectable. Generator tests cover repeated identical output,
missing artifacts, stale OpenAPI, stale TypeScript, and non-mutating checks.

Only `/health` is implemented. Future domain routes and MCP tools in the design
are not exported until their backend capabilities exist. See the
[client package](../libs/typescript/api-client/README.md) for usage.

Generated drift is separate from API compatibility. `scripts/check-contracts`
now compares against a [frozen foundation checkpoint](baselines/README.md) with
a pinned oasdiff container, enforced by root validation and CI. No API has been
released yet; the checkpoint is not described as a released contract. Additive
evolution remains the policy; breaking changes and baseline updates require
human review.

Generator reference: [openapi-typescript Node API](https://openapi-ts.dev/node).
