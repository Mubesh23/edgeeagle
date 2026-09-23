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

There is no event publication, durable quarantine, HTTP
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

## Initial event acceptance

`notifications.EventAccepted.for_candidate(...)` creates a validated publication
intent with explicit stable notification ID, occurrence timestamp, correlation ID,
and causation ID. It references the accepted canonical event and lineage digest.
`identity.acceptance_key(candidate)` owns that deterministic digest (unchanged
from receipt format 1). See [event contracts](../../../contracts/events/README.md).
The notification type and `EventPublicationRepository` port are transport-neutral.
Its `accept_with_notification(candidate, notification)` method requires atomic
canonical acceptance and outbox insertion. Exact retries reuse the original
notification metadata. The persistence adapter implements it; no publisher exists
yet. Legacy `accept` remains persistence-only and does not gain a notification on
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
does not replace the caller's retained immutable fixture context. Event publication
and API exposure remain next steps.

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
