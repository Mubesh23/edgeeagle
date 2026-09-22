# ADR — Polyglot Monorepo

**Status:** Accepted  
**Date:** 2026-09-22

## Context

A single repo improves cross-platform contract changes, atomic documentation, CI, agent context, and shared versioning without requiring a runtime monolith.

## Decision

Use one repository for TypeScript product surfaces/infrastructure and Python quantitative/backend workloads, with explicit contracts and independent deployment boundaries.

## Consequences

Split only when security, ownership, release cadence, or scaling creates a concrete reason.

## Related

- `docs/architecture/TDD.md`
- `docs/product/PRD.md`
