# Local Development & Testing Strategy

**Status:** Draft  
**Local AWS emulator:** Floci

## Goal

A normal developer or coding agent should be able to bootstrap, run, and validate the project without AWS credentials and without paid sports-data API calls.

## Local stack

Implemented foundation: `compose.yaml` pins PostgreSQL 17.11-alpine3.23 and
Floci 2.1.0, plus a stdlib-only synthetic provider mock on Python 3.11.16.
Docker with Compose v2.15+ must be running. `scripts/local-up`
starts project `edgeeagle-local` and waits for health checks. Initial image
downloads require internet access, but no provider or AWS credentials.

Host ports bind only to 127.0.0.1: PostgreSQL 55432 and Floci 4566. Override using
exported `EDGEEAGLE_POSTGRES_PORT` / `EDGEEAGLE_FLOCI_PORT`; use the same values
for all commands. No environment file needs to be copied. PostgreSQL uses
database/user `edgeeagle` and the public local-only password `edgeeagle-local`.
These credentials are never production configuration.

`scripts/local-down` removes project containers and its Compose network, while
preserving `edgeeagle-local_postgres-data` and `edgeeagle-local_floci-data`.
It never requests volume deletion or removal of unrelated containers.
No Docker socket is mounted in Floci; its UI sidecar is disabled.
Floci explicitly uses persistent storage mode. The native 2.1.0 image's supplied
`/usr/local/bin/healthcheck.sh` is used; unlike the JVM Dockerfile, this image
does not contain wget. This image difference was verified during local startup.

`scripts/test-integration` starts the stack, checks a PostgreSQL temporary-table
transaction, and checks Floci S3 put/get with a unique temporary bucket. Test
resources are cleaned up; PostgreSQL application data is not reset. AWS SDK
clients use explicit dummy credentials, an explicit loopback endpoint, path-style
S3, and disabled proxies. Profile/config discovery is disabled in the wrapper.
Python socket connections are restricted to 127.0.0.1 during integration tests.

`scripts/validate` includes these tests and leaves healthy containers running for
development. Unit tests remain separately network-blocked. Queue/DLQ consumers
arrive in subsequent increments; the diagram
below describes the target stack, not additional implemented services.

Full validation also runs OpenAPI compatibility in a pinned, network-disabled
Docker container and npm/Python dependency advisory scans. Initial image/package
downloads and current public advisory queries require internet access, but no
provider or AWS credentials. See [scan scope](security-scanning.md). Advisory
service failures fail validation rather than being reported as clean scans.

The provider mock runs on host loopback port 9080 (override with exported
`EDGEEAGLE_MOCK_PROVIDER_PORT`). It serves synthetic soccer odds plus deterministic
empty, rate-limit, server-error, and malformed responses, with no upstream calls.
`local-up` rebuilds its image so fixture edits cannot leave a stale container.
See [mock usage](../../tests/mock_providers/README.md) and
[fixture provenance](../../tests/fixtures/providers/README.md). No live provider
compatibility is claimed by these tests.

The Alembic framework is implemented under `apps/api/migrations`. After starting
services, run `scripts/migrate` to establish its empty baseline and
`scripts/migrate current` to inspect it. Migration round-trip tests run in their
own temporary database; they never downgrade/reset the application database.
See [migration operations](../../apps/api/migrations/README.md).

Image sources verified 2026-09-22:
[official PostgreSQL images](https://github.com/docker-library/official-images/blob/master/library/postgres)
and [Floci 2.1.0](https://github.com/floci-io/floci/releases/tag/2.1.0).

```text
Docker/containers
  PostgreSQL
  Floci :4566
  Mock provider server

Processes
  API
  Worker
  Web
  MCP
  Mobile separately through Expo
```

## Floci

Floci is the standard local emulator for AWS-shaped services. Application AWS clients use an endpoint override in local/test environments. Local credentials are dummy/test values.

Floci should emulate the AWS services we actually depend on; unsupported or behaviorally important differences must be documented rather than hidden.

`cdk synth` remains the baseline infrastructure validation and does not require Floci or AWS credentials.

## External provider testing

External providers are **not** emulated by Floci.

Each provider adapter must have:

1. Captured fixture payloads
2. Adapter unit tests
3. HTTP-level mock-provider integration tests
4. A small optional provider-contract test against free/demo/replay access

## Test tiers

### Tier 1 — Unit

- No network
- No cloud
- $0
- Run on every iteration

Examples: market normalization, odds conversion, de-vigging, pricing, EV, model math, strategy filters, settlement, risk.

### Tier 2 — Local integration

- PostgreSQL + Floci + provider mock server
- No real AWS credentials
- No paid provider calls
- Run before review

Validate queues/DLQs, storage adapters, migrations, API, events, and end-to-end fixture ingestion.

### Tier 3 — Provider contract

Small, separately-invoked/scheduled tests against:

- Kalshi Demo/public endpoints
- Sportmonks free plan
- The Odds API free plan within a strict credit budget
- Polymarket documented API endpoints
- SportsDataIO Replay when integrated

These detect schema/auth behavior drift. They are not the main CI feedback loop.

### Tier 4 — Deployed integration

Non-production AWS and paid/production provider access only when needed. Human/CI controlled.

## Required async tests

Any queue/event handler needs tests for:

- normal processing
- duplicate delivery/idempotency
- retryable error
- terminal error
- DLQ behavior
- additive unknown fields

## Provider fixtures

Store sanitized fixtures under `tests/fixtures/providers/<provider>/`. Include metadata recording endpoint/API version/capture date. Do not commit secrets or payloads whose license forbids redistribution.

## Canonical commands

- `scripts/bootstrap`
- `scripts/local-up`
- `scripts/local-down`
- `scripts/test-unit`
- `scripts/test-integration`
- `scripts/test-provider-contracts`
- `scripts/validate`
- `scripts/synth`

## Floci source

Official project: https://github.com/floci-io/floci
