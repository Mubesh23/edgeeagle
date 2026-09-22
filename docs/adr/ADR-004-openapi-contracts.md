# ADR — OpenAPI Contract Strategy

**Status:** Proposed  
**Date:** 2026-09-22

## Context

One contract reduces drift across web, mobile, MCP, and backend.

## Decision

Treat generated OpenAPI as the external client contract, generate TypeScript clients, and enforce additive/backward-compatible evolution by default.

## Consequences

Generated code is protected output.

## Related

- `docs/architecture/TDD.md`
- `docs/product/PRD.md`
