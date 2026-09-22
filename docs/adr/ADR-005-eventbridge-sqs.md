# ADR — EventBridge + SQS Async Architecture

**Status:** Proposed  
**Date:** 2026-09-22

## Context

Provides decoupling, buffering, retries, fan-out, and failure isolation without a heavier streaming platform.

## Decision

Use EventBridge for domain-event routing and a dedicated SQS queue/DLQ per async consumer. Assume at-least-once delivery.

## Consequences

Consumers must be idempotent.

## Related

- `docs/architecture/TDD.md`
- `docs/product/PRD.md`
