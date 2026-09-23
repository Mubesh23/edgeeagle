# Documentation Index

This directory contains the product, architecture, data, testing, cost, and implementation documents for the Multi-Sport Quantitative Betting & Trading Platform.

## Reading order

1. [`product/PRD.md`](product/PRD.md) — what the product must do and why.
2. [`architecture/TDD.md`](architecture/TDD.md) — how the platform is designed.
3. [`product/feature-specs/parlay-lab.md`](product/feature-specs/parlay-lab.md) — detailed Parlay Lab product behavior and acceptance criteria.
4. [`architecture/reference-patterns.md`](architecture/reference-patterns.md) — patterns intentionally adopted from the supplied reference architecture/agent docs.
5. [`data/provider-evaluation.md`](data/provider-evaluation.md) — current provider capabilities, free tiers, test environments, and pricing.
6. [`adr/ADR-011-data-provider-venue-strategy.md`](adr/ADR-011-data-provider-venue-strategy.md) — provider/venue decision and rationale.
7. [`architecture/canonical-domain-model.md`](architecture/canonical-domain-model.md) — canonical sports, market, provider, portfolio, and execution entities.
8. [`architecture/data-ingestion-normalization.md`](architecture/data-ingestion-normalization.md) — raw ingestion, normalization, provenance, event-time semantics, and entity resolution.
9. [`architecture/api-mcp-contracts.md`](architecture/api-mcp-contracts.md) — API and MCP boundaries.
10. [`development/local-development-testing.md`](development/local-development-testing.md) — Floci, fixtures, mock providers, and test tiers.
11. [`operations/cost-quota-strategy.md`](operations/cost-quota-strategy.md) — free-tier-first validation and provider/AWS budget controls.
12. [`development/monorepo-engineering-guide.md`](development/monorepo-engineering-guide.md) — package boundaries, commands, generated code, and agent-readiness.
13. [`roadmap/implementation-roadmap.md`](roadmap/implementation-roadmap.md) — implementation sequence and acceptance gates.
14. [`adr/`](adr/) — architecture decision records.

## Document authority

Phase 2 mapping design: [ADR-013 — immutable provider mapping revisions](adr/ADR-013-provider-mapping-revisions.md).
Physical storage: [ADR-014 — PostgreSQL mapping history](adr/ADR-014-provider-mapping-storage.md).
Raw storage: [ADR-015 — immutable captures](adr/ADR-015-raw-payload-storage.md).
Offline acquisition: [ADR-016 — ingestion boundary](adr/ADR-016-offline-ingestion-boundary.md).
Fixture normalization: [ADR-017 — event candidates](adr/ADR-017-synthetic-event-normalization.md).
Transactional acceptance: [ADR-018 — event receipts and replay](adr/ADR-018-event-acceptance-lineage.md).
Publication intents: [ADR-019 — initial event outbox](adr/ADR-019-event-outbox.md).
Delivery coordination: [ADR-020 — fenced leases](adr/ADR-020-outbox-delivery-leases.md).

- **PRD** owns product requirements and product-level non-functional requirements.
- **TDD** owns architecture and technical implementation decisions.
- **Feature specs** own detailed behavior and acceptance criteria for substantial product capabilities that would otherwise overload the master PRD.
- **ADRs** own individual architecture decisions and their rationale.
- **Provider evaluation** owns fast-changing vendor facts such as pricing, quotas, test environments, and API coverage.
- **Domain/API/data design docs** own detailed contracts that would make the PRD or TDD too volatile.

Vendor facts must include a `Last verified` date. Do not duplicate vendor pricing across multiple documents unless the duplicate is explicitly labeled a snapshot.
