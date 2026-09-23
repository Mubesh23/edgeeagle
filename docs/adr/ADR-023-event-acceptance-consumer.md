# ADR-023 — Event acceptance verification consumer

**Status:** Accepted for Phase 2 local consumer validation  
**Date:** 2026-09-23

## Decision

The first consumer verifies `EventAccepted` against the immutable publication intent
and its normalization receipt, then records that verification once. It does not
create another canonical event store, model output, or API projection. Ingestion
owns queue/handler ports and `consume_one`; persistence owns SQS decoding and the
PostgreSQL implementation. No new deployable or worker loop is introduced.

Migration `0008_event_consumption` creates `event_acceptance_consumptions`, keyed by
notification ID with a restrictive FK to the immutable outbox and a database-time
verification timestamp. It is specific to this verification consumer, not a global
deduplication table for future consumers. UPDATE/DELETE/TRUNCATE are prohibited.
The handler validates the original notification and receipt on every invocation,
including duplicates, and inserts with ON CONFLICT DO NOTHING. Concurrent exact
deliveries converge; changed notification metadata fails closed. Caller-owned
transactions commit the verification and deduplication effect together. Downgrading
removes this consumer's receipts and permits reprocessing; it is not an operational
reset and requires review outside disposable tests.

Receive outside the database transaction, handle inside a fresh commit-on-success
transaction, then delete the SQS message outside it. Delete failure/crash can replay
an already committed effect. The latest receipt handle is transport state, never
the domain deduplication key. Empty short-poll results do not prove an empty backlog.
Do not delete on decode, verification, transaction, or handler errors. SQS visibility
and a bounded redrive policy retain failures for retry, eventually isolating poison
messages. No immediate discard, automatic DLQ replay, or exactly-once claim.

The decoder validates the EventBridge source/detail type and version-1 notification,
including non-null publication time at/after occurrence. Unknown additive fields
are ignored at the transport boundary; known fields remain mandatory and validated.
Duplicate JSON keys, nonfinite constants, and bodies over 96 KiB are rejected.
The authored producer schema and strict pending-intent reader remain unchanged.
Publication time may differ across retries without creating a different effect.

## Approved local routing scope

The user approved Floci-only disposable queues, DLQs, monitoring checks, and exact
test-rule/queue permission policies. No production IAM/CDK/network changes are
authorized. Use standard queues, one consumer-processing DLQ, and a separate
EventBridge target-delivery DLQ. Terminal DLQs are monitored holding queues, not
automatically consumed queues requiring recursive DLQs. Source retention is shorter
than DLQ retention. Redrive allow policy names only the source queue. EventBridge
SendMessage policies name only the exact rule ARN and target/DLQ ARN.

Queue-depth probes report visible, in-flight, and delayed counts; local tests check
backlog and nonempty DLQ signals. These are monitoring primitives, not hosted alarms
or proof that Floci enforces AWS authorization. Production alarms, supervision,
operator runbooks, access controls, and tuning remain future work.

## Validation

Network-blocked tests cover decoding, additive fields, validation errors, SDK
responses, and commit-before-delete. Disposable PostgreSQL tests cover concurrent
duplicates, changed identity, rollback, receipt immutability, and migrations.
Floci tests cover routing, duplicate effects, retry, delete-loss replay, poison
redrive, and queue/DLQ depth. Emulator gaps must be reported, never papered over
by manually placing a message in the DLQ and calling it a redrive test.

AWS references verified 2026-09-23:

- [SQS receive and receipt handles](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/APIReference/API_ReceiveMessage.html)
- [SQS redrive and retention](https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/sqs-dead-letter-queues.html)
- [EventBridge target-delivery DLQs](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-rule-dlq.html)
- [Scoped SQS policies](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-use-resource-based.html)
