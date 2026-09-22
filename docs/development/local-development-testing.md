# Local Development & Testing Strategy

**Status:** Draft  
**Local AWS emulator:** Floci

## Goal

A normal developer or coding agent should be able to bootstrap, run, and validate the project without AWS credentials and without paid sports-data API calls.

## Local stack

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
