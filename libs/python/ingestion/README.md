# Raw ingestion library

This library implements the first acquisition capability, `OfflineDatasetImporter`,
and `ingest_raw(importer, store)`. It depends inward on `edgeeagle-domain`, not
PostgreSQL, S3, API, or provider SDKs. It is not a worker or deployable.
The `offline` adapter implements bounded file reads; the `service` module knows
only the importer and storage protocols. See
[ADR-016](../../../docs/adr/ADR-016-offline-ingestion-boundary.md).

```python
from pathlib import Path

from edgeeagle_ingestion.offline import LocalFileImporter
from edgeeagle_ingestion.service import ingest_raw

# Caller supplies validated RawCapture and a RawPayloadStore implementation.
importer = LocalFileImporter(Path("retained-fixture.json"), capture, max_bytes=4096)
reference = ingest_raw(importer, store)
```

The path is trusted local configuration, never an untrusted API parameter. Choose
an explicit byte limit appropriate for the resource. Empty/non-JSON/malformed
bytes are retained without parsing. The adapter does not read sidecar metadata,
infer timestamps, or claim retention rights. Errors propagate without retries.
The returned reference proves the store acknowledged the expected capture;
durability/integrity guarantees belong to the chosen store implementation.

Reuse unchanged files and the same capture metadata for replay. A file changed
between calls represents different content, not an identical retry. Research
should replay retained references or pinned inputs, not mutable local files.
Ingestion time is supplied by the caller; synthetic fixture quote times must
not be promoted to observed/available-at evidence.

The raw acquisition operation does not publish events. There is no durable quarantine, HTTP
acquisition, provider quota logic, real provider adapter, or source/venue catalog
registration. Other capability-specific interfaces will be added with their
first consumers.

## Synthetic event candidates

`synthetic_events.normalize_fixture_events(store, reference, bindings)` reads
retained raw bytes and returns immutable `events.EventCandidate` records.
This fixture-only adapter implements the event subset of the authored odds
fixture, not a live provider contract or market/quote normalizer. See
[ADR-017](../../../docs/adr/ADR-017-synthetic-event-normalization.md).

Each `FixtureEventBinding` explicitly supplies the source-scoped event key,
exact competition/home/away labels, canonical event ID, sport/competition/season,
canonical home/away participants, status, and context version. No IDs, seasons,
statuses, or availability timestamps are inferred. Labels are exact guards on a
caller-supplied binding, not global participant identifiers or fuzzy matching.
The fixture context is not authenticated review evidence or production mapping
history. Preserve immutable versioned contexts alongside retained references.

The adapter verifies checksum and length before parsing, rejects malformed or
ambiguous batches, and validates canonical relationships with the domain validator.
All candidates retain the raw reference, source-scoped provider event key, parser
version `synthetic-odds-events-v1`, normalizer version
`synthetic-event-bindings-v1`, and caller's context version. Unknown fields stay
in raw storage and are ignored by this event projection; prices are not validated.
Errors return no partial batch and leave raw storage unchanged. Candidates are
neither persisted events nor historically eligible datasets. The separate
`EventAcceptanceRepository` port now supports initial canonical persistence;
normalization itself still performs no writes.

## Mapping-backed reference resolution

`fixture_references.resolve_fixture_references(keys, mappings, sports, as_of=...)`
now resolves explicitly authored sport/competition/season/home/away keys through
complete mapping histories and reads the selected canonical records. It returns
frozen references, the UTC cutoff, and five selected revisions in that role order.
Missing, revoked, future-only, malformed, wrong-type, or inconsistent references
fail closed; no writes, retries, label matching, or event creation occur.

Supply both repository ports from the same pinned read-only snapshot; this
port-level helper cannot enforce PostgreSQL isolation. It is tested offline and
feeds the mapped normalizer below. Do not discard its revision evidence to use
legacy receipts. Explicit fixture event IDs, label guards,
status, and context versions remain necessary. See
[ADR-025](../../../docs/adr/ADR-025-mapping-backed-fixture-context.md) for the
approved format-1 compatibility and incremental format-2 rollout. Run
`scripts/test-unit tests/unit/test_fixture_references.py` for focused coverage.

`synthetic_events.normalize_mapped_fixture_events(store, reference, requests,
reads, as_of=...)` accepts frozen `MappedFixtureRequest` manifests instead of
canonical reference records. Each manifest supplies source-scoped reference keys
and the explicit event ID, labels, status, and context version. The function reads
and verifies raw bytes and exact batch coverage before opening one `reads()`
snapshot. It resolves all references through `FixtureReferenceResolver`, closes
the snapshot, and returns candidates with `FixtureMappingEvidence` and normalizer
version `synthetic-event-mappings-v1`. Parser and legacy normalizer versions do
not change. Empty batches need no snapshot; any failure returns no partial batch.
No canonical writes, mapping decisions, publication, or retries occur here.
The factory must own a fresh pinned read-only snapshot for the entire batch;
the persistence factory `fixture_reference_reads(engine)` supplies this composition.
Retain returned candidates
for exact retries: a fresh database snapshot is not a historical replay dataset.

`synthetic_events.replay_mapped_fixture_events(store, reference, candidates)`
reproduces a complete capture using trusted retained format-2 candidates, with no
current mapping or canonical-reference reads. It requires parser
`synthetic-odds-events-v1`, normalizer `synthetic-event-mappings-v1`, and retained
mapping evidence before reading storage. It verifies raw size/hash, exact event
coverage and label guards, then compares the entire reconstructed candidate,
ignoring participant-entry order and equivalent timestamp offsets. Results follow
raw event order; any mismatch fails the batch. Even an empty capture is read and
verified. No writes, acceptance, or publication occur. Use
`scripts/test-unit tests/unit/test_fixture_replay.py` for offline coverage and
`scripts/test-integration -k mapped_normalization` for PostgreSQL/Floci coverage.

Replay preserves captured evidence after later corrections/revocations; it does
not authorize fresh normalization or prove the supplied receipt is authentic.
Authored event ID, status, context version, and reference values are replay inputs,
not independently verified facts. Unknown availability stays unknown. Format-1
receipts have no retained mapping context and are deliberately unsupported here.

## Initial event acceptance

Candidates now optionally carry `FixtureMappingEvidence`: resolved canonical
references with selected mapping revisions and cutoff, plus explicit fixture
label guards. Candidate validation ties that evidence to source, event references,
and HOME/AWAY entries. Format-2 serialization includes all evidence in the lineage
digest; legacy candidates omit the new field and retain format-1 bytes/digests.
The dual-format reader and schema migration `0009_mapped_receipts` are implemented;
mapped normalization now uses the pinned composition described above. Neither this value object
nor decoding proves authenticated review or historical eligibility.

`notifications.EventAccepted.for_candidate(...)` creates a validated publication
intent with explicit stable notification ID, occurrence timestamp, correlation ID,
and causation ID. It references the accepted canonical event and lineage digest.
`identity.acceptance_key(candidate)` owns that deterministic digest (unchanged
from receipt format 1). See [event contracts](../../../contracts/events/README.md).
The notification type and `EventPublicationRepository` port are transport-neutral.
Its `accept_with_notification(candidate, notification)` method requires atomic
canonical acceptance and outbox insertion. Exact retries reuse the original
notification metadata. Persistence implements both this repository and the separate
EventBridge publisher. Legacy `accept` remains persistence-only and does not gain a notification on
replay. See [ADR-019](../../../docs/adr/ADR-019-event-outbox.md).

`events.EventAcceptanceRepository.accept(candidate)` returns True for first
acceptance, False for an exact replay, and raises `EventAcceptanceConflict` for
conflicting accepted output/lineage. `get(event_id)` returns the immutable accepted
candidate, not current event state. The PostgreSQL adapter lives in persistence,
which depends inward on ingestion; this package has no database dependency.
See [ADR-018](../../../docs/adr/ADR-018-event-acceptance-lineage.md).

Acceptance requires preexisting canonical references and source registration.
The raw capture, provider key, and transformation/context versions identify the
acquisition independently of output event ID. This is initial insertion only,
not updates, multi-source reconciliation, or historical eligibility. Retain raw
bytes before accepting; the database cannot verify S3 durability. Receipt lineage
does not replace the caller's retained immutable fixture context. Publication uses
the dispatcher and outer EventBridge adapter. Current-state API exposure and the
composed fixture-to-API acceptance test now exist; this is not a hosted worker.

`delivery.OutboxDeliveryRepository` now describes leased delivery coordination:
claim one intent, acknowledge a live claim, schedule its retry, and inspect state.
`DeliveryClaim` and `DeliveryState` are validated immutable application values;
their timestamps are operational, not research availability. Persistence implements
the port with PostgreSQL timing. The dispatcher below sequences transactions;
the EventBridge adapter is implemented in persistence.
See [ADR-020](../../../docs/adr/ADR-020-outbox-delivery-leases.md).

## Bounded dispatch

The complementary `consumer.consume_one(queue, transactions)` receives a validated
notification outside a transaction, verifies/records it with `EventAcceptedHandler`
inside a fresh transaction, and acknowledges the queue only after commit. Exceptions
propagate without deleting the message. PROCESSED and DUPLICATE both permit deletion;
IDLE means only an empty receive. PostgreSQL implements the first receipt-verification
handler; concrete SQS transport follows separately. See
[ADR-023](../../../docs/adr/ADR-023-event-acceptance-consumer.md).

`dispatch.dispatch_one(transactions, publisher, lease_for=..., retry_after=...)`
claims at most one intent, commits before sending, and acknowledges in a fresh
transaction. It returns IDLE, PUBLISHED (broker acceptance, not consumption), or
RETRY_SCHEDULED. Only `RetryablePublicationError` schedules a retry; unexpected
errors, configuration errors, interrupts, lease loss, and commit failures propagate.
No loop, sleep, terminal discard, or hidden resend is performed.

Supply a fresh commit-on-success, rollback-on-error repository context each time;
it must close its connection and never suppress exceptions or join an outer
transaction. For PostgreSQL, a caller-owned `@contextmanager` can yield
`PostgresOutboxDeliveryRepository(connection)` inside `with engine.begin()`.
The publisher receives the immutable claim, preserves notification identity,
checks broker acceptance, and bounds its transport calls within the lease.
Neither protocol creates clients or discovers credentials.

Crash recovery may resend the same notification after lease expiry. Consumers
must deduplicate; this is not exactly-once delivery. EventBridge transport now lives
in persistence alongside SQS transport and queue-depth probes. Disposable local tests
cover processing-DLQ redrive; EventBridge delivery-DLQ forwarding remains a documented
emulator gap. Worker composition and hosted monitoring remain unimplemented.
See [ADR-021](../../../docs/adr/ADR-021-outbox-dispatch-boundary.md).
`scripts/test-integration -k dispatch` verifies actual PostgreSQL commit/rollback
boundaries with a recording publisher, not Floci event delivery.

Root commands include this package in lint/typecheck, tests, and Python builds:

```sh
scripts/test-unit tests/unit/test_ingestion.py
scripts/test-integration -k fixture_ingestion
scripts/validate
```

Unit tests disable network. Integration uses the existing synthetic fixture and
Floci with disposable buckets and PostgreSQL databases, loopback endpoints, and
dummy credentials only.
`scripts/build` regenerates ignored ingestion wheels/sdists under root `dist/`.
