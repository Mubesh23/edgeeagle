# Domain event contracts

`event-accepted.v1.json` is an authored JSON Schema (2020-12), not generated output.
The ingestion `EventAccepted` value owns canonical serialization; network-blocked
unit tests validate its output against this schema. Run
`scripts/test-unit tests/unit/test_event_notifications.py` or `scripts/validate`.

Envelope `event_id` identifies the notification. `payload.canonical_event_id`
identifies the sports event; `payload.acceptance_key` identifies its immutable
normalization receipt lineage. Consumers must resolve that receipt, not assume
current event state is the original accepted output. Occurrence/publication times
are operational timestamps, never substitutes for data `available_at`.

The outbox stores pending envelopes with `published_at: null`. The EventBridge publisher
supplies a publication-attempt time at or after occurrence in the delivered copy.
The schema accepts both states; temporal ordering is also enforced by the Python
serializer. IDs and occurrence/trace metadata remain unchanged across retries.
The bounded dispatcher, EventBridge publisher, and SQS verification consumer now
exist; there is no worker loop. The consumer validates known fields while allowing
additive delivered fields and deduplicates by notification identity, not publication
time. See [consumer scope and emulator gap](../../docs/adr/ADR-023-event-acceptance-consumer.md) and
[publisher scope](../../docs/adr/ADR-022-eventbridge-outbox-publisher.md).

There is no released event baseline. Future evolution is additive by default;
breaking event/schema changes require human review. See
[ADR-019](../../docs/adr/ADR-019-event-outbox.md).
