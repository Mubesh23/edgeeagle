# ADR — Versioned Deterministic Strategy Rules

**Status:** Proposed  
**Date:** 2026-09-22

## Context

Prevents historical/live logic divergence and makes research reproducible.

## Decision

Represent strategies as versioned deterministic rules reusable in backtest, live scan, paper, and future execution.

## Consequences

Do not embed LLM decisions in strategy execution.

## Related

- `docs/architecture/TDD.md`
- `docs/product/PRD.md`
