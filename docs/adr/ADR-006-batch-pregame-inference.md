# ADR — Batch Pregame Inference

**Status:** Proposed  
**Date:** 2026-09-22

## Context

Simpler, reproducible, cheaper, and easier to debug than an online model server for V1.

## Decision

Pregame predictions are generated asynchronously and persisted; user request paths read stored predictions.

## Consequences

True low-latency live inference is deferred.

## Related

- `docs/architecture/TDD.md`
- `docs/product/PRD.md`
