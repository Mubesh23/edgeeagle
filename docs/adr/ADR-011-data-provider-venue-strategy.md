# ADR — Data Provider & Venue Strategy

**Status:** Proposed  
**Date:** 2026-09-22

## Context

No single provider best serves sports fundamentals, sportsbook aggregation, historical bootstrap, and tradable order books. The split reduces lock-in and lets us exploit free/demo access during validation.

## Decision

Use provider-neutral adapters; separate DataSource from Venue. V1 sources are Sportmonks, The Odds API, Kalshi, Polymarket, and Football-Data.co.uk, with SportsDataIO/Sportradar evaluated later.

## Consequences

Fast-changing pricing/quotas live in the provider matrix.

## Related

- `docs/architecture/TDD.md`
- `docs/product/PRD.md`
