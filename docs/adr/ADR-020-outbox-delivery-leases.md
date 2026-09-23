# ADR-020 — PostgreSQL outbox delivery leases

**Status:** Accepted for Phase 2 local delivery coordination  
**Date:** 2026-09-23

## Decision

Keep ADR-019 envelopes immutable. Add a separate `event_outbox_delivery` row per
intent with PENDING, LEASED, or PUBLISHED state, attempt count, eligibility time,
claim/expiry times, and acknowledgement time. This is mutable operational state,
not historical research data or an append-only attempt audit.

Migration `0007_outbox_delivery` initializes existing intents as PENDING and adds
an AFTER INSERT outbox trigger so old and new writers create delivery state in the
same transaction. Initial eligibility is the later of database time and envelope
occurrence. This does not manufacture past delivery/acceptance timestamps or
backfill missing intents for legacy persistence-only receipts. Downgrade removes
only delivery state and its initializer; intent/receipt data is preserved. Once a
publisher exists, downgrade/reupgrade could redeliver acknowledged intents and
must not be used as an operational reset without human review.

Ingestion owns `DeliveryClaim`, `DeliveryState`, and `OutboxDeliveryRepository`.
Persistence implements `claim(lease_for)`, `acknowledge(claim)`, `retry(claim,
retry_after)`, and `get(notification_id)`. Use caller-owned READ COMMITTED write
transactions. Each operation has a savepoint; no hidden commit, engine, or network
call. PostgreSQL `clock_timestamp()` is the timing authority, read after taking
the row lock for completion. Application clocks cannot extend stale leases.

Claim one due PENDING or expired LEASED row using `FOR UPDATE SKIP LOCKED` and
increment its attempt number atomically. The pair (notification ID, attempt)
fences completion; expired or superseded claims raise `DeliveryLeaseLost`, as do
repeated acknowledgements/retries after completion. Acknowledgement means the
caller observed broker acceptance, not consumer completion. The adapter cannot
verify this without a publisher. Retry makes the row PENDING at database-now plus
an explicit delay. Attempt count is retained, not reset. Reads validate state.

Lease duration must be positive and at most one hour; retry delay positive and
at most one day. These are API safety bounds, not production tuning. No heartbeat,
automatic backoff, attempt cap, terminal discard, error-body storage, or admin
reset is introduced. Failed workers become eligible on expiry. Poison envelopes
fail closed and remain retained; quarantine/alerting must precede unattended use.
Database clock regressions can delay eligibility; this is not a monotonic-clock
or exactly-once guarantee. Selection order is best effort, not strict FIFO.

## Required future relay sequence

1. Claim in a short transaction and COMMIT before any external send.
2. Publish outside the database transaction with bounded transport timeouts.
3. Acknowledge success or schedule retry in a new short transaction.

A crash after send but before acknowledgement can republish the same notification
ID. Fencing protects database state, not an already-running network call; consumers
must deduplicate. No dispatcher, AWS adapter, queue, DLQ, deployment, IAM change,
or monitoring is delivered by this storage increment. Add these next using Floci,
and validate broker partial failures and consumer idempotency before production.

## Validation

Test distinct concurrent claims, SKIP LOCKED behavior, expiry/reclaim, stale
completion fencing, delayed retry, acknowledgement exclusion, malformed state,
operation/outer rollback, initial-state backfill, migration round trips, and
immutability of the original envelope. Use disposable local databases and no sleeps
for expiry tests (test-only SQL advances operational state into the past).
