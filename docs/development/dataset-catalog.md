# Private retained-dataset catalog

The catalog is a read-only **local operator interface**, with a CLI and an opt-in
local API, not a hosted service or web screen. It selects trusted ADR-029
whole-season roots explicitly; it neither
scans buckets nor creates a PostgreSQL registry. See
[ADR-031](../adr/ADR-031-local-dataset-catalog.md).

## Configuration

Keep a JSON file inside the repository's ignored `.data/` directory. For example,
`.data/dataset-catalog.json` has this shape; replace both placeholders with your
existing private bucket and the exact retained lowercase 64-character root hash:

```json
{
  "format": 1,
  "bucket": "YOUR_LOCAL_RESEARCH_BUCKET",
  "entries": [
    {
      "root_hash": "YOUR_TRUSTED_ROOT_SHA256",
      "label": "Private results season"
    }
  ]
}
```

Use an `edgeeagle-private-research-...` bucket (synthetic tests use
`edgeeagle-raw-test-...`). This command does not create it. A label is an operator
annotation, not a verified competition name or substitute for the root identity.
Configuration accepts at most 32 unique roots, 120 characters per label and
16 KiB total. Unknown/duplicate JSON fields, duplicate roots, unsupported format,
invalid hashes, control-character labels, oversized/nonregular files and paths
outside `.data/` are rejected. Symlinks cannot redirect reads outside that boundary.
An empty catalog is valid. Different buckets require separate configuration files.

## Commands

With the retained objects available in local Floci:

```sh
scripts/datasets --catalog .data/dataset-catalog.json list
scripts/datasets --catalog .data/dataset-catalog.json inspect YOUR_TRUSTED_ROOT_SHA256
```

`list` retrieves only roots and emits `{items: [...]}` in root-hash order. Each
item contains `metadata` and `replay_status: NOT_CHECKED`. Metadata includes the
operator label, source ID, full raw reference and timestamps, parser/normalizer
versions, declared row count and page count. It does not claim pages/raw still
exist or that the capture has been replayed.

`inspect` accepts only a selected root, retrieves and verifies the complete
capture, and emits one result only after every page and raw row passes replay.
It reports `VERIFIED`, completion time, verified receipt/participant counts,
asserted kickoff range, canonical scope IDs and retained context versions.
Completion time records this observation, not a durable storage guarantee.
Subsequent listing remains `NOT_CHECKED`; inspecting again performs fresh reads.

Both responses include `usage: REPLAY_ONLY`, `backtest_eligible: false`, and
stable exclusion reasons:

- `REPLAY_ONLY_CONTRACT`: this format is not historical decision-input data.
- `CONTEXT_AVAILABILITY_UNPROVEN`: retained mappings/context do not establish
  historical availability for every consumed fact.
- `RAW_AVAILABILITY_UNKNOWN`: present when raw `available_at` is null.

A known raw timestamp removes only the last reason, never the restriction.
Kickoffs remain retained assertions; successful replay does not independently
verify their accuracy. Inspection explicitly does not verify database acceptance
or provider rights. It does not authorize training, features, backtests or trading.

The CLI emits JSON to stdout, errors to stderr and exits nonzero on failure.
No partial successful JSON, silent omissions, provider fetches, repairs, store
writes, SQL connections or persisted verification status are performed. Treat
configuration/output as private data and keep saved output out of Git/hosted CI.

Only loopback Floci is used, with explicit dummy credentials, disabled proxies,
3-second connect/5-second read timeouts and at most one SDK retry. Override the
usual `EDGEEAGLE_FLOCI_PORT` if needed; no remote endpoint is accepted. The
existing raw/page size limits still apply, and clients close on failure as well
as success. No AWS credentials, paid APIs or production resources are required.

## Validation and next boundary

```sh
scripts/test-unit tests/unit/test_dataset_catalog.py tests/unit/test_dataset_cli.py
scripts/test-integration -k catalog_cli
scripts/validate
```

Synthetic integration verifies unchanged stored objects after listing/inspection,
then deliberately removes a test-owned page: root metadata still lists, but
inspection fails without repair. No private capture is used in routine tests.

Only ADR-029 season roots are supported initially, not the older ADR-026 envelope
formats. Those identities are not interchangeable. A web/MCP consumer,
durable catalog publication/consistency rules, multi-user access, and hosted
display remain separate increments and reviews. API/client contracts now have
additive private catalog reads under
[ADR-032](../adr/ADR-032-local-dataset-api.md); see
[local API setup](../../apps/api/README.md). The default app still has no catalog
configured. The HTTP list and inspection preserve these same replay-only results,
use no-store responses and never persist verification status. No web/MCP consumer
or hosted access is added.

## Local inspection evidence — 2026-09-23

The approved private EPL 2024/25 root was registered in ignored local catalog
configuration and inspected with the operator command. Listing reported 380
declared rows and six pages with `NOT_CHECKED`; fresh complete replay returned
380 verified receipts and 20 participants. The retained context version identifies
the owner-approved London-offset assumption; it is not independent kickoff proof.
Unknown raw availability remained null and all three exclusion reasons remained
present. No provider download, store write, PostgreSQL connection, rights upgrade
or historical-eligibility change was part of the catalog command. Private
configuration and any saved output remain outside Git and routine tests.

A separate read-only comparison against the retained backup report confirmed
that all eight source objects retained their keys, sizes and ETags.

`scripts/validate` passed: 863 Python unit tests, 140 integration tests and one
documented Floci expected failure, plus generated-contract checks, formatting,
linting, typechecking, OpenAPI compatibility, builds, credential-free CDK synthesis
and dependency advisory scans. The 20 targeted catalog unit tests achieved 100%
statement coverage for the two new Python modules; the synthetic CLI integration
also passed independently. Unchanged TypeScript tasks used local Turbo cache.
Existing Starlette deprecations and the resource-free CDK skeleton warning remain.
Hosted CI and fresh-checkout validation were not run in this local session.

## Local API inspection evidence — 2026-09-23

The opt-in factory was exercised through the in-process HTTP test client using
the approved ignored catalog configuration. Listing returned one `NOT_CHECKED`
entry; fresh inspection returned `VERIFIED`, 380 receipts and 20 participants,
with `backtest_eligible=false` and `Cache-Control: no-store`. Before/after local
Floci listings confirmed all eight source objects were unchanged. No listening
server, provider download, PostgreSQL connection or hosted exposure was started.

The new HTTP route and local factory modules each achieved 100% statement coverage
in targeted network-blocked tests. A separate disposable Floci integration verified
65 authored receipts and missing-page rejection through the configured HTTP app.

Full `scripts/validate` passed with 875 Python unit tests, 141 integration tests
and the existing single Floci expected failure. Generated drift, formatting,
linting, strict typing, client tests, additive OpenAPI compatibility, builds,
credential-free CDK synthesis and dependency advisory scans passed. Turbo reused
unchanged tasks; changed client and web checks executed. Existing Starlette/CDK
warnings remain. Hosted CI, a fresh checkout and a listening-server smoke test
were not run; this evidence covers local in-process HTTP plus real Floci storage.
