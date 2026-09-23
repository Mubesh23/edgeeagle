# Persistence and outbox transport adapters

`edgeeagle-persistence` depends inward on `edgeeagle-domain` and
`edgeeagle-ingestion` and implements their repository protocols using SQLAlchemy
connections and the psycopg driver.
Importing the package opens no database connection. The API has no dependency on
this package yet; no endpoint, deployment, database configuration, or schema
migration is introduced by these adapters.

## Immutable raw S3 captures

`S3RawPayloadStore(client, bucket)` implements the domain `RawPayloadStore` port.
The caller supplies an already-configured synchronous boto3 S3 client and existing
bucket; importing the adapter does not discover credentials or create resources.
Use explicit dummy credentials and the Floci loopback endpoint locally. Timeouts,
SDK retries, client closing, and retention rights belong to the caller.

`put(RawPayload)` returns a `RawPayloadReference`; `get(reference)` returns verified
bytes or None only for `NoSuchKey`. Preserve the reference for replay and reads.
Exact bytes are retained, including empty/non-JSON bodies. Capture metadata and
payload SHA-256 determine the versioned key. Replays preserve original timestamps;
different capture metadata creates a distinct object even for identical bytes.
Conditional writes never overwrite. Existing objects must match exact bytes and
metadata; corruption raises `RawPayloadIntegrityError`, while other service errors
propagate. The adapter closes each response body, but not the caller's client.

See [ADR-015](../../../docs/adr/ADR-015-raw-payload-storage.md) for format limits
and identity. This initial in-memory interface is for bounded responses, not
streaming archives. It is not Object Lock, a cross-S3/PostgreSQL transaction, an
ingestion pipeline, a catalog, or a licensing policy. There is no delete method,
production bucket/IAM change, provider call, or API wiring.

Unit tests verify preconditions, integrity, errors, limits, and timezone identity.
`scripts/test-integration -k raw_storage` checks Floci conditional-write enforcement,
concurrent replay, exact byte retention, capture separation, and corruption in
unique disposable buckets. Cleanup removes only those test buckets and objects.

## Current scope

`PostgresDataSourceRepository` and `PostgresVenueRepository` provide `add` and
`get` for the records and capability sets introduced by migration
`0002_source_venue`. Source and venue IDs remain separate types and namespaces.
Reads reconstruct validated, immutable domain records. A single joined SELECT
reads each record and its capability set from the same statement snapshot.
An absent canonical ID returns `None`; malformed stored data raises rather than
being silently repaired. SQL values are bound parameters.

Inserts are deliberately **not upserts**: an existing identity raises the
inward-owned `DuplicateRecordError`, including when the incoming record matches.
This is not ingestion replay/idempotency handling. There are no update, delete,
list, or historical/as-of operations for these source/venue records yet.

## Sports and event records

`PostgresSportsRepository` implements the inward-owned `SportsRepository` port
for migration `0003_sports_events`: `add_sport`/`get_sport`, competition, season,
participant, and event equivalents, plus `get_event_participants`.
Each reference record must be inserted before its dependents. Foreign keys reject
missing references; callers can include the whole hierarchy in one transaction.

`add_event(event, entries)` requires an immutable tuple of entries. It resolves
the already-persisted sport, competition, season, and participants, then calls the
existing pure `validate_event_context` before inserting. Missing references or
inconsistent context raise `ValueError`; wrong input types raise `TypeError`.
The event and all entries share one savepoint. The adapter derives the redundant
storage-only entry `sport_id` from the validated event; callers cannot supply it.
Database foreign keys remain the final guard against concurrent reference changes.
No sport-specific team count, role uniqueness, or season-date containment is added.
At least one entry is required, without claiming a sport's roster is complete.

Reads reconstruct domain records; event and entry reads are separate statements.
Entry results are immutable tuples ordered by opaque participant ID, not sporting
rank. An absent event or an event inserted directly with no entries produces an
empty entry tuple; `get_event` distinguishes them. Reads do not certify a complete
resolved event context. Callers needing a consistent view across several reads
must choose suitable transaction isolation (for example REPEATABLE READ) and
invoke domain validation as needed. Timestamps preserve instants, not original
offsets or timezone labels. No historical/as-of query is implied.

## Mapping history and replay

`PostgresMappingRepository` implements the domain `MappingRepository` port over
migration `0004_mapping_history`. Its methods are:

- `append(revision)`: under a per-key row lock, accept the next proposed revision
  or return an identical existing revision. `(key, revision)` is the stable replay
  identity. Changed content or a skipped revision raises `MappingConflictError`.
  Do not refresh timestamps or blindly renumber a delivery on retry.
- `history(key)`: return the complete, validated, ordered tuple of visible revisions.
- `resolve(key, as_of=...)`: load complete visible history, then use the pure
  resolver's availability cutoff. Revocation returns None without falling back.

Mapping writes require READ COMMITTED isolation so a blocked writer sees the
previous writer's commit after taking the key lock. The key and revision share
a savepoint; failed validation or missing canonical references leave no partial
key. Existing references are enforced by SQL foreign keys. No counter, updates,
or deletes are used. Stored history is validated even for old replays and earlier
as-of queries. A malformed future revision fails closed. Changing the target kind,
decreasing decision availability/ingestion, or revoking a different target fails.

All mapping timestamp comparisons and returned records use UTC instants; equal
Decimal values are equivalent despite display scale. The caller supplies the
proposed number; only the next number is accepted under the lock. There is no
unconditional auto-number operation. For repeatable multi-read research, the
caller can use a pinned REPEATABLE READ transaction, but cannot append within it.
An as-of cutoff does not substitute for dataset snapshots or no-lookahead checks
on other data. Reading full histories is intentionally linear in history length.

## Initial event acceptance

`PostgresEventAcceptanceRepository` implements the ingestion-owned
`EventAcceptanceRepository` port over `EventCandidate`. Migration
`0005_event_acceptance` retains immutable accepted-output snapshots with raw capture,
provider key, parser/normalizer/context versions, and a unique lineage digest.
`accept(candidate)` returns True for initial insertion and False for exact replay.
Different output or lineage for an accepted event, a legacy event without a
receipt, or the same lineage targeting a second event raises
`EventAcceptanceConflict`. No updates or automatic source reconciliation occur.

The event, entries, and receipt share a savepoint in the caller's READ COMMITTED
transaction. Missing references or receipt insertion failures leave no partial
event even if caught by the caller. Competing initial writers converge or conflict;
there are no hidden commits or retries. Entries are compared in participant-ID
order, and timestamp offsets normalize to UTC. `get(event_id)` reconstructs and
validates the accepted snapshot, including its indexed identities, from one SELECT.
Malformed receipts fail closed. Receipt UPDATE/DELETE/TRUNCATE is prohibited.

Replay also compares current event and entries under an event row lock, rejecting
detected drift. Direct SQL writers changing child rows without taking that parent
lock are outside this insertion-only protocol. This is not a historical event
versioning policy. The caller retains raw bytes before acceptance and preserves
the referenced immutable normalization context; receipts store accepted output and
lineage, not a full context catalog. This legacy method creates no outbox intent;
use the publication-aware method below for that guarantee. The separate dispatcher
and EventBridge publisher now support publication; no cross-S3 transaction or API
path exists yet. See
[ADR-018](../../../docs/adr/ADR-018-event-acceptance-lineage.md).

Run `scripts/test-integration -k 'event_acceptance or fixture_ingestion'` for
concurrent exact/conflicting retries, identity collisions, rollback, immutability,
and the Floci raw-to-PostgreSQL acceptance path. Unit tests in
`tests/unit/test_event_acceptance.py` validate candidates and the private codec.

## Shared transaction ownership

### Publication-aware acceptance

Use `PostgresEventAcceptanceRepository.accept_with_notification(candidate, notification)`
for new publication-aware workflows. Construct the ingestion `EventAccepted`
notification with `for_candidate`, supplying a stable ID, occurrence time, and
correlation/causation IDs once, then reuse them on retry. The new method implements
`EventPublicationRepository` and atomically inserts event, entries, normalization
receipt, and immutable `event_outbox` intent. Missing/conflicting replay metadata
raises `EventAcceptanceConflict`; an outbox identity collision rolls back all new
canonical writes even when the caller catches it.

`get_notification(EventId)` loads and validates the pending intent and receipt
identity. `published_at` remains null: this repository does not publish anything.
Legacy `accept` remains persistence-only; a legacy receipt with no outbox conflicts
if passed to the new method. There is no automatic backfill or repair. Pending
intents cannot be updated/deleted/truncated. Delivery coordination is described
below; queues and monitoring remain future increments. See
[ADR-019](../../../docs/adr/ADR-019-event-outbox.md) and
[event contracts](../../../contracts/events/README.md).

Run `scripts/test-integration -k 'outbox or fixture_ingestion'` for transactional
publication intent and fixture-to-outbox coverage. Tests use disposable resources;
the developer application database is not migrated automatically.

## Delivery coordination

`PostgresOutboxDeliveryRepository(connection)` implements the ingestion
`OutboxDeliveryRepository` port over migration `0007_outbox_delivery`:

- `claim(lease_for=timedelta(...))` locks one eligible pending or expired intent
  with SKIP LOCKED, increments attempts, and returns a validated `DeliveryClaim`.
  None means no eligible unlocked work at that instant, not an empty backlog.
- `acknowledge(claim)` marks broker acceptance only for the matching unexpired
  claim. It does not prove downstream consumption or perform any network call.
- `retry(claim, retry_after=timedelta(...))` releases that live claim into PENDING
  with a future eligibility time; attempt count is retained.
- `get(notification_id)` returns validated operational state or None.

Writes require READ COMMITTED and a caller-owned transaction. Eligibility uses
database statement time; claim/completion timing uses database wall-clock time
after taking the row lock. Stale, expired, completed, and rolled-back claim handles
raise `DeliveryLeaseLost`. A retry/acknowledgement is not silently accepted twice.
Lease bounds are (0, one hour]; retry bounds are (0, one day].

Commit the claim before publishing outside the transaction, then acknowledge or
retry in a new short transaction. The caller owns timeouts and retry policy.
Crash recovery can duplicate an external send; notification ID stays stable for
consumer deduplication. This adapter provides no heartbeat, scheduler, publisher,
terminal retry cap, monitoring, or DLQ. Poison receipts remain retained and fail
closed; quarantine/alerting is needed before unattended operation. Operational
state is not an immutable attempt history. See
[ADR-020](../../../docs/adr/ADR-020-outbox-delivery-leases.md).

`scripts/test-integration -k delivery` exercises real PostgreSQL locking, fencing,
expiry recovery, rollback, and migration initialization. Tests only manipulate
uniquely named disposable databases; no application database is migrated.

## EventBridge publication

`eventbridge.EventBridgePublisher(client, bus_arn, clock=...)` implements ingestion's
`EventPublisher` and can be passed to `dispatch_one`. It uses an explicit existing
standard/custom bus ARN, describes that destination before every send, and publishes
one `EventAccepted` envelope with source `edgeeagle.ingestion`. Only its delivered
copy receives a UTC publication-attempt timestamp; IDs/lineage and the stored intent
remain unchanged. The EventBridge transport ID never replaces the notification ID.

Configure the caller-owned boto3 client with `retries={"mode": "standard",
"total_max_attempts": 1}` and positive connect/read timeouts of at most five seconds.
Use explicit dummy credentials, disabled proxies, and a Floci loopback endpoint in
local tests. The adapter creates/closes no client or infrastructure. It imports no
database code and must run outside the claim transaction. The publisher adds no
runtime dependency beyond the package's existing boto3 dependency; EventBridge
typing stubs are development-only.

The adapter checks a socket-time allowance against the remaining lease before
describe and before put. This is not a hard process deadline; clock synchronization,
database fencing, and crash recovery still matter. Detail has an application-specific
64 KiB UTF-8 limit. Acceptance requires a consistent successful HTTP/entry response.
Transient/ambiguous failures become `RetryablePublicationError`; configuration and
non-retryable failures propagate. SDK service errors preserve their cause; raw
provider error messages are not copied into the adapter's exception messages.

Bus preflight cannot prevent deletion between describe and put. Stable resource
lifecycle and downstream routing/consumer monitoring are prerequisites for unattended
operation. Broker acceptance does not mean consumer delivery; consumer deduplication,
queues/DLQs, monitoring, and worker composition remain next increments.
See [ADR-022](../../../docs/adr/ADR-022-eventbridge-outbox-publisher.md).

`scripts/test-integration -k eventbridge` verifies Floci broker acceptance, PostgreSQL
acknowledgement, stable-ID replay after a simulated crash, and missing-bus rejection.
Tests create/delete only their own uniquely named buses and disposable databases.
There are no targets or queues in this test scope; no IAM enforcement is claimed.

## Transaction ownership details

For PostgreSQL repositories, the caller supplies an active PostgreSQL/psycopg SQLAlchemy connection transaction,
normally through `with engine.begin() as connection`. Autocommit is rejected.
Pass the same connection to repositories to commit or roll back their work
together. The adapters never commit, roll back the outer transaction, close the
connection, create an engine, or read environment credentials.

Each insert uses a savepoint so that a dependent-row failure also removes its
parent insert. A caller may catch an operation error and continue its transaction;
otherwise the error propagates to the transaction context and rolls back the
entire batch. Unique violations become `DuplicateRecordError`; other SQLAlchemy
database exceptions propagate, preserving their cause. Transaction retries and
error-to-HTTP translation belong to future application orchestration, not here.
Locks remain held until the caller commits/rolls back. Keep transactions short;
the caller configures lock/statement timeouts and deterministic multi-key ordering
to avoid deadlocks. No automatic retry or changes to engine settings are hidden here.
Repository instances must not be shared across threads or used outside their
supplied connection's active transaction. Async API callers must not execute
these synchronous operations directly on an event loop.

These are current-state reference stores, not backtest datasets, authorization
policy, or evidence that descriptive capabilities permit execution. Caller IDs
must already be allocated; no provider catalog or ID-generation policy is added.
Alembic remains the schema authority; adapters do not create tables or enable
ORM metadata/autogeneration.

## Validation

From repository root:

```sh
scripts/bootstrap
uv run --locked --offline --all-packages pytest libs/python/persistence/tests
scripts/test-integration -k repository
scripts/validate
```

Unit tests run without network. Integration tests create and migrate uniquely
named disposable PostgreSQL databases and drop only those databases afterward.
They cover empty/nonempty capabilities, independent IDs, bound SQL values,
commit visibility, multi-repository rollback, duplicate rejection, continued
transactions after failure, partial-write rollback, and autocommit rejection.
Sports tests also cover hierarchy round trips, optional fields, timezone instants,
12-participant events, repeated roles, invalid resolved contexts, reference FK
failures, duplicate identities, and atomic event/entry rollback.
Mapping tests cover all six target types, correction/revocation, exact replays,
conflicts, first-key/existing-key concurrent writers, transaction rollback,
history corruption, and repeatable-read snapshots. No API/ingestion mapping path
or reviewer-authentication workflow is implemented by this adapter.
No paid provider or AWS credentials are used.

Root checks include this package; `scripts/build` regenerates its ignored sdist
and wheel under root `dist/`.
