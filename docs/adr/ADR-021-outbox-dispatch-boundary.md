# ADR-021 — Bounded outbox dispatcher

**Status:** Accepted for Phase 2 dispatcher orchestration  
**Date:** 2026-09-23

## Decision

Implement ADR-020's relay sequence as `ingestion.dispatch.dispatch_one`.
Ingestion owns a transport-neutral publisher protocol and transaction-factory
type. The factory returns a fresh repository context that commits on normal
exit, rolls back on error, closes its connection, and never suppresses errors.
It must not participate in an outer transaction. Composition supplies these
adapters; ingestion imports neither SQLAlchemy nor an AWS SDK.

One invocation claims at most one intent, exits the claim transaction before
calling the publisher, then acknowledges in a new transaction. No eligible work
returns IDLE. Observed broker acceptance followed by committed acknowledgement
returns PUBLISHED, not proof of consumer completion. A classified transient or
ambiguous publication error schedules the explicit bounded delay in a new
transaction and returns RETRY_SCHEDULED. No internal loop or sleep is introduced.

Only `RetryablePublicationError` is handled. Configuration, malformed payload,
unexpected errors, interrupts, lost leases, and transaction failures propagate.
An unacknowledged committed claim remains recoverable after lease expiry.
If sending succeeded but acknowledgement failed, recovery can send the same
notification again. No new notification ID is allocated; consumers must deduplicate.
Permanent errors require operator intervention before unattended operation; this
increment does not add quarantine, terminal discard, or pretend retry solves them.

Publisher implementations must verify broker acceptance (including entry-level
errors) and bound network retries/timeouts within the lease. The dispatcher does
not invent a broker receipt or use an application clock to override database
fencing. Python protocol contracts cannot prevent a misbehaving custom adapter;
composition and integration tests must prove the transaction boundary.

## Scope and validation

This increment implements orchestration only, not an EventBridge adapter, worker
loop, queue, IAM policy, deployment, consumer, DLQ, or monitoring. Those remain
required before the Phase 2 event-to-API path and unattended operation are complete.
No event schema, database schema, or public API changes are needed.

Network-disabled tests cover send-after-commit, idle work, retry scheduling,
unclassified failure, interruption, both commit failures, and lease fencing.
Disposable PostgreSQL integration verifies committed claim visibility during
publication, rollback, and crash/replay with stable notification identity.
