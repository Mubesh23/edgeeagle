# Reference Architecture Patterns Adopted

**Status:** Informational  
**Source set:** `atoz-webapps-architecture.md`, `executive-summary-brd-prd.md`, `cross-app-comparison-matrix.md`, `10-ai-agentic-development-guide.md`, `12-agent-instruction-templates.md`, `13-agentic-workflow-playbook.md`

This document records the engineering patterns intentionally learned from the supplied reference material. It is not a claim that this project should copy the source systems wholesale.

## Adopted patterns

### Thin client-facing aggregation boundary

Use a BFF/API layer to aggregate downstream capabilities and shape client responses, but do not let the BFF become a second system of record.

### Workload-specific persistence

Choose persistence and compute based on workload rather than applying one database or execution model everywhere. Transactional/current state, historical analytical data, search, and event-driven workloads have different needs.

### Monorepo with explicit package direction

Keep root-level commands and document package dependency direction. Add nested instructions only where a package genuinely differs in commands, generated-code behavior, infrastructure safety, or ownership.

### Contract-first, additive evolution

API/event/schema changes are additive by default. Generate consumers from contracts where practical and test the intermediate deployment state.

### Event-driven idempotency as an invariant

Queue/event consumers assume at-least-once delivery, use idempotency keys/conditional effects, and have DLQs plus explicit retry/DLQ validation.

### Credential-free fast feedback loop

Local unit/integration validation should not require cloud credentials. Emulators, fixtures, replay data, and mock servers are preferred over granting agents/developers broader credentials.

### Agent documentation as a system

`AGENTS.md` is canonical; tool-specific files point to it. It must document commands, generated/protected paths, runtime dependencies, ownership, invariants, safety restrictions, and definition of done.

### Separate maintained rationale from generated context

Architecture rationale, invariants, and known limitations are human-maintained. Machine-derived inventories and generated clients/schemas may be regenerated and checked for drift.

### Explicit verification states

Distinguish:

1. Verified — check ran and passed.
2. Not verifiable here — check exists but requires unavailable infrastructure/credentials.
3. No check exists — a known validation gap, not a pass.

### Persist long-running work state

Task plans, decisions, commands/validation results, unresolved risks, and handoff state should live in the repository rather than only in chat context.

## Patterns deliberately not copied

- We do not adopt DynamoDB everywhere simply because it dominates the reference estate.
- We do not create micro-frontends or many microservices without a product-specific reason.
- We do not carry forward missing correlation IDs; correlation/causation IDs are first-class here.
- We do not make credential-dependent tests the normal development loop.
- We do not place fast-changing provider pricing in the PRD/TDD; it lives in the provider matrix.
