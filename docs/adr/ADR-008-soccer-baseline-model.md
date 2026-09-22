# ADR — Interpretable Soccer Baseline

**Status:** Proposed  
**Date:** 2026-09-22

## Context

Provides a transparent baseline that can be calibrated and beaten OOS before adding complexity.

## Decision

Start with team strength plus recency-aware attack/defense, home advantage, xG features where available, and a Poisson/Dixon-Coles-style score distribution.

## Consequences

Model selection remains empirical.

## Related

- `docs/architecture/TDD.md`
- `docs/product/PRD.md`
