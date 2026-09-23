# ADR-022 — EventBridge outbox publisher

**Status:** Accepted for Phase 2 local broker publication  
**Date:** 2026-09-23

## Decision

Implement ingestion's `EventPublisher` in `edgeeagle_persistence.eventbridge`.
This package already holds the outer PostgreSQL/S3 adapters and their boto3
dependency. Extend it narrowly to outbox transport rather than create another
package or deployable for one adapter. Ingestion/domain remain SDK-free; the
publisher neither opens a database transaction nor changes an outbox intent.

The caller supplies a synchronous EventBridge client and explicit standard/custom
bus ARN (no implicit default bus or partner bus). Require standard retry mode,
one total SDK attempt, and positive connect/read timeouts of at most five seconds
each. No hidden retry loop, credential discovery, resource creation, client close,
or environment lookup occurs inside the adapter. The caller owns client lifetime.

Before each send, describe the configured bus and require its returned ARN to
match. Send exactly one `EventAccepted` entry with source `edgeeagle.ingestion`,
detail type `EventAccepted`, occurrence as EventBridge `Time`, and the full versioned
envelope as JSON `Detail`. Preserve notification/trace IDs and lineage. Stamp only
the delivered copy's `published_at` with an injectable aware UTC attempt clock
immediately before the put. Limit the UTF-8 detail to 64 KiB as an application
safety bound, not a statement of the AWS service maximum.

Check remaining lease time before describe and again before put, reserving the
configured socket timeout allowance plus one second for completion. Clock skew
before claim time fails closed. These are conservative send guards, not a hard
wall-clock deadline: DNS, process pauses, or clock changes can exceed socket
timeouts. Database fencing remains authoritative and duplicate sends remain
possible. Production composition requires clock synchronization and supervision.

Require HTTP 200, exactly one result, integer zero `FailedEntryCount`, a nonblank
broker `EventId`, and no entry error fields before returning acceptance. Never
replace the domain notification ID with the broker's transport ID. Retryable entry
errors are `InternalFailure` and `ThrottlingException`. Classify connection/timeout
ambiguity, HTTP 429/5xx, documented transient request errors, and malformed success
responses as retryable. Other service/entry errors fail closed and propagate;
configuration/authorization errors require operator intervention, not blind retries.

## Limits

AWS can report successful puts to a nonexistent bus. Describe mitigates a stale
or mistyped destination, but cannot prevent deletion between describe and put.
Keep the bus stable; controlled lifecycle changes and routing/consumer health
monitoring are required before unattended use. Acceptance is not proof of routing,
target delivery, or consumer processing. This increment creates no queues, policies,
worker loop, production deployment, deduplication store, DLQ, or monitoring.

## Validation and references

Network-disabled SDK stub tests cover wire format, per-entry failures, invalid
responses, size/time guards, missing/mismatched bus, and SDK configuration.
Local Floci tests create/delete only uniquely named disposable buses and compose
real broker calls with PostgreSQL dispatcher acknowledgement and crash replay.
These validate broker acceptance, not consumer delivery or AWS IAM enforcement.
No paid providers or real AWS credentials are used.

AWS semantics verified 2026-09-23:

- [PutEvents failures and nonexistent buses](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-putevents.html)
- [Retryable and non-retryable entry errors](https://docs.aws.amazon.com/eventbridge/latest/APIReference/API_PutEventsResultEntry.html)
- [Boto3 PutEvents contract](https://docs.aws.amazon.com/boto3/latest/reference/services/events/client/put_events.html)
