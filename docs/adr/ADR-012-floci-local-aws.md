# ADR — Floci for Local AWS Emulation

**Status:** Accepted  
**Date:** 2026-09-22

## Context

The project explicitly requires low-cost local validation without AWS credentials. Floci supports AWS-shaped local workflows and keeps cloud dependencies out of the fast test loop.

## Decision

Use Floci as the standard local AWS emulator for development and routine integration tests.

## Consequences

External sports providers still use fixtures/mock servers; CDK synth remains independent.

## Related

- `docs/architecture/TDD.md`
- `docs/product/PRD.md`
