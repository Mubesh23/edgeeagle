# ADR — PostgreSQL + S3/Parquet Storage

**Status:** Proposed  
**Date:** 2026-09-22

## Context

The domain is relational while historical odds/features/backtests are append-heavy analytical data.

## Decision

Use PostgreSQL for canonical transactional/current state and S3/Parquet for immutable/raw/historical analytical datasets and artifacts.

## Consequences

Avoid forcing all data into either relational tables or a single NoSQL model.

## Related

- `docs/architecture/TDD.md`
- `docs/product/PRD.md`
