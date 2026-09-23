# ADR-019 — Initial event notification outbox

**Status:** Accepted for Phase 2 fixture ingestion  
**Date:** 2026-09-23

## Decision

Add `EventAccepted` version 1 under `contracts/events/`, with the TDD envelope
fields: `event_id` (notification identity, not sports event identity), `event_type`,
`version`, `occurred_at`, `published_at`, `correlation_id`, and `causation_id`.
The payload contains `canonical_event_id` and `acceptance_key`, referencing the
immutable normalization receipt. It does not duplicate raw bodies or mutable
current state. No provider schema, credentials, or storage location is included.

Ingestion owns the immutable notification value and publication repository port.
Callers allocate a stable notification ID and supply occurrence/trace metadata;
an exact retry must reuse all of it. `occurred_at` is the application acceptance
operation's timestamp, not kickoff, provider observation, or research availability.
It must not precede raw ingestion. Trace IDs identify the ingestion workflow and
causing command/acquisition; callers must not invent upstream tracing evidence.
Pending intents contain `published_at: null`. A future transport adapter will
populate a publication-attempt timestamp without changing the immutable intent.
Delivered messages must have a non-null `published_at >= occurred_at`.

Add `accept_with_notification(candidate, notification)` alongside the existing
ADR-018 `accept(candidate)`. The new operation composes event/entries/receipt and
outbox insertion inside one savepoint in the caller's READ COMMITTED transaction.
It returns True on insertion, False only on exact candidate AND notification replay.
Different metadata or reused notification identity conflicts. A receipt created by
the older persistence-only method without a notification conflicts on this new
method; no silent repair/backfill or fabricated historical acceptance timestamp.
The existing method keeps its behavior for compatibility, but does not promise
publication. Publication-aware orchestration must use the new method exclusively.

Migration `0006_event_outbox` creates `event_outbox` with notification ID primary
key, unique canonical event FK to the receipt, and a JSONB envelope. Identity/type/
version/pending-state checks guard storage. UPDATE/DELETE/TRUNCATE are prohibited.
Readers validate the envelope and its receipt identity. No legacy rows are changed
or backfilled. Downgrade removes only this table and its own trigger function.

The outbox is an immutable intent log, not yet a delivery queue. A later additive
delivery-state table/relay will track claims, attempts, acknowledgements, retries,
and monitoring. At-least-once publication requires consumer deduplication by the
stable notification ID; an acknowledgement loss may republish that same ID.
No exactly-once transport, S3 transaction, ordering, or backtest eligibility is
claimed. No worker, AWS client, SQS queue, DLQ, IAM, deployment, or HTTP API is added.

## Contracts and validation

The JSON Schema is authored, not generated. Its owner is ingestion's notification
contract; tests validate canonical serialization against it. Version 1 permits
pending null publication timestamps; transport must enforce the delivered-state
rule. No released event compatibility baseline exists yet. Future changes are
additive by default and breaking changes require human review.

Test invalid envelope values, exact/conflicting/concurrent replay, foreign keys,
immutable storage, collision-induced full savepoint rollback, outer rollback,
commit visibility, and the retained-fixture path. Run credential-free root
validation; local PostgreSQL tests use disposable databases only.
