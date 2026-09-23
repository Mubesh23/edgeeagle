# Draft upstream report — EventBridge target-delivery DLQ

**Status:** Draft only; not submitted  
**Observed:** 2026-09-23  
**Image:** `floci/floci:2.1.0`

## Suggested title

EventBridge: failed SQS target delivery is logged but not forwarded to DeadLetterConfig

## Scope

This concerns EventBridge event-bus rule targets, not EventBridge Scheduler,
Pipes, Lambda asynchronous destinations, or SQS consumer redrive. Successful
EventBridge-to-SQS delivery and SQS processing-DLQ redrive work in the same setup.

## Reproduction

Against local Floci, using explicit dummy AWS credentials and region `us-east-1`:

1. Create a uniquely named custom event bus and standard SQS delivery-DLQ queue.
2. Create a rule matching source `edgeeagle.ingestion` and detail type `EventAccepted`.
3. Set the DLQ resource policy to allow `events.amazonaws.com` to perform
   `sqs:SendMessage` on that exact queue ARN, conditional on `aws:SourceArn`
   matching the exact rule ARN.
4. Call `PutTargets` with an SQS target ARN whose queue does not exist,
   `DeadLetterConfig: {Arn: <delivery-DLQ ARN>}`, and
   `RetryPolicy: {MaximumRetryAttempts: 0, MaximumEventAgeInSeconds: 60}`.
5. Call `PutEvents` on the bus with the matching source/detail type and detail
   `{"failure_probe":true}`. Both calls return `FailedEntryCount: 0`.
6. Poll the delivery DLQ for ten seconds. It remains empty.
7. Remove the test target/rule, queues, and bus. No persistent application data
   or production resources are involved.

## Expected and actual

Expected: a terminal target-delivery failure reaches the configured delivery DLQ,
with the event and applicable failure metadata. Broker acceptance alone does not
imply successful target delivery.

Actual: no DLQ message. The Floci log reports the failed target send with
`The specified queue does not exist.` The pinned
[EventBridgeInvoker source](https://github.com/floci-io/floci/blob/2.1.0/src/main/java/io/github/hectorvent/floci/services/eventbridge/EventBridgeInvoker.java)
catches target exceptions and logs them without forwarding to the DLQ.

Reference: [AWS EventBridge dead-letter queues](https://docs.aws.amazon.com/eventbridge/latest/userguide/eb-rule-dlq.html).
This report does not claim AWS IAM-policy enforcement was validated in Floci.

## EdgeEagle regression evidence

The executable local reproduction is
[`test_eventbridge_target_failure_reaches_delivery_dlq`](../../tests/integration/test_sqs_consumer.py).
Run from the repository root with Docker available:

```sh
scripts/test-integration -k target_failure --runxfail
```

This diagnostic is expected to **exit nonzero** on the pinned image. Normal
validation retains a strict, narrowly typed expected failure so unrelated setup
or SDK errors cannot be mislabeled as this gap. No test manually inserts a DLQ
message to simulate successful forwarding.

Before submitting upstream, recheck for a duplicate report and attach a standalone
SDK reproduction if requested. No issue, PR, fork, or emulator patch has been
published by this session. See [ADR-023](../adr/ADR-023-event-acceptance-consumer.md)
for the current readiness limitation and expected-failure removal gate.
