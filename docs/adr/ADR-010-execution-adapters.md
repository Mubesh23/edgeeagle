# ADR — Execution Adapter Architecture

**Status:** Proposed  
**Date:** 2026-09-22

## Context

Lets the same strategy/risk pipeline progress from simulation to controlled execution without rewriting business logic.

## Decision

Define a venue-neutral execution abstraction beginning with paper execution; add venue-specific real adapters later.

## Consequences

Execution credentials and submission remain server-side and permissioned.

## Related

- `docs/architecture/TDD.md`
- `docs/product/PRD.md`
