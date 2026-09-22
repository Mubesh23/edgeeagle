# ADR — FastAPI BFF

**Status:** Proposed  
**Date:** 2026-09-22

## Context

Python keeps API/domain logic close to modeling/pricing while OpenAPI generation supports web/mobile clients.

## Decision

Use a Python FastAPI BFF/application API for V1. It validates/authenticates/aggregates but owns no authoritative business data.

## Consequences

Revisit only if scale/ownership requires another service boundary.

## Related

- `docs/architecture/TDD.md`
- `docs/product/PRD.md`
