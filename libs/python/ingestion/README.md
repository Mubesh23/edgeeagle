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

## Replay dataset metadata

`manifests.ManifestCapture(raw=..., candidates=(...))` and
`ReplayDatasetManifest(captures=(...))` are immutable replay-only values.
`encode_manifest(manifest, codec)` returns canonical envelope bytes containing the
content-derived `dataset_version`, full receipt pins, and capture metadata.
`decode_manifest(body, codec)` verifies strict structure, supported versions,
duplicates, hashes, and byte-for-byte canonical encoding. Both codec paths enforce
the inclusive 1 MiB envelope limit; reads reject oversize input before JSON parsing.
Builders canonicalize capture/pin order, while wire readers reject noncanonical
ordering rather than repair it. The pure `EventReceiptCodec` port keeps receipt
serialization in persistence; `edgeeagle_persistence.receipts.EventReceiptCodec`
implements it using the format-1/2/3 codec without database access.

The fixed `REPLAY_ONLY` usage is not historical eligibility. Structural validation
does not verify raw storage, complete capture coverage, or actual acceptance;
even an empty receipt group still needs raw verification. See
[ADR-026](../../../docs/adr/ADR-026-replay-dataset-manifest.md) and run
`scripts/test-unit tests/unit/test_dataset_manifest.py tests/unit/test_mapped_receipts.py`.
Golden vectors were independently assembled from the contract and existing receipt
codec before manifest implementation; they are test expectations, not generated
artifacts to refresh automatically when serialization changes.

`snapshot_replay.verify_manifest(body, codec, store)` now performs the separate
read-only artifact check. It validates all metadata before reading raw data, then
reuses `replay_mapped_fixture_events` for each complete capture. It returns an eager
tuple of candidate groups, in canonical capture order and raw event order inside
each group, retaining empty groups. A failure anywhere raises instead of returning
a verified prefix; exceptions propagate without retries. It performs no writes,
database/current-reference lookups, or publication. Callers own storage configuration
and transport timeouts. Run `scripts/test-unit tests/unit/test_snapshot_replay.py`
and `scripts/test-integration -k snapshot_replay` for offline and PostgreSQL/Floci
coverage. Verification does not change `REPLAY_ONLY`, authenticate acceptance, or
guarantee future artifact availability.

`manifest_storage.ReplayManifestStore` defines immutable canonical-envelope writes
and exact dataset-version reads. `put(body)` returns the validated dataset version;
`get(version)` returns exact validated bytes or None only for an absent object.
Stored corruption raises `ManifestIntegrityError`; service/transport errors propagate.
Persistence supplies the S3 adapter under
[ADR-027](../../../docs/adr/ADR-027-replay-manifest-storage.md). Storage performs no
raw reads or replay verification. Retrieve-by-version replay composition with
retained PostgreSQL receipts is tested by `scripts/test-integration -k snapshot_replay`;
no catalog is present. Call `get(version)`, explicitly handle None, then pass the
returned bytes to `verify_manifest`. Never reconstruct missing metadata from current state.

## Football-Data results CSV adapter

`football_data.normalize_results(raw_store, reference, requests, reads, as_of=...)`
accepts the bounded ADR-028 subset from retained raw bytes. `FootballDataRequest`
supplies an explicit canonical event ID, five mapping keys, exact labels/division,
context version, and per-row UTC offset. `row_locator` constructs the adapter's
source-scoped locator; it is not a native provider match ID. All rows must be
covered exactly once. One pinned reference snapshot supplies the complete batch.

`replay_results(raw_store, reference, candidates)` reproduces the complete capture
from retained format-3 evidence, without current reference reads or writes.
Kickoff, scores, coverage, and output must agree. Unknown availability remains
unknown. Inputs are UTF-8 CSV completed results with dd/mm/yyyy and HH:MM, limited
to 100 rows/1 MiB; extra named columns stay raw-only. No odds, missing-time/date-only
records, automatic downloads, identity matching, or backtest eligibility are added.
See the [authored fixture](../../../tests/fixtures/providers/football_data/README.md).
Run `scripts/test-unit tests/unit/test_football_data.py`.
Manifest construction selects `FOOTBALL_DATA_RESULTS_REPLAY` for nonempty CSV
capture groups; mixed CSV/synthetic manifests are rejected. The existing strict
codec, immutable storage port and `verify_manifest` support that kind without
changing original synthetic manifest bytes.

`football_data_import.import_results_dataset` composes raw acquisition, normalization,
batch acceptance and readback in one caller-owned transaction, then manifest storage
after commit. It returns the content-derived dataset version. It publishes no events
and adds no application database setup. See the
[workflow guide](../../../docs/development/football-data-import.md) for prerequisites,
composition, failure/retry semantics, and the local acceptance command.

## Initial event acceptance

ADR-029 adds `football_data.normalize_season_results` and `replay_season_results`
for complete captures up to 512 rows with a distinct parser pin. They share the
strict field rules and projection with the original 100-row profile, which stays
unchanged. Season candidates require the separate paged replay bundle,
not ADR-026 manifests. No real-data import or historical eligibility is implied.
Run `scripts/test-unit tests/unit/test_football_data_season.py` for the new bounds.

`season_bundle` supplies canonical root/page codecs and `verify_bundle` through
the inward-owned `SeasonObjectStore` port. A root pins up to eight 64-receipt pages
and one unchanged raw capture; verification validates all metadata before the raw
read and requires complete-capture replay. Roots are limited to 64 KiB, pages to
1 MiB. Persistence supplies `S3SeasonObjectStore`. The separate
`football_data_season_import.import_season_dataset` retains raw bytes, accepts
all rows in one transaction, builds the bundle before commit, then stores pages
and finally the root. It returns the acknowledged root hash, not backtest eligibility.
See
[ADR-029](../../../docs/adr/ADR-029-football-data-season-replay.md) for the exact wire
contract and `scripts/test-unit tests/unit/test_season_bundle.py` for offline tests.

Optional `SoccerResultEvidence` adds validated full-time goals and an asserted
per-row UTC offset to finished soccer candidates. Format-3 receipts preserve it;
legacy candidates omit it from serialization and identity. This is retained result
evidence, not settlement or historical eligibility. CSV ingestion follows
[ADR-028](../../../docs/adr/ADR-028-football-data-results-import.md).

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

## Authored market import

`market_import.import_market_fixture(importer, store, bindings, transactions)`
composes bounded local acquisition, immutable raw retention, full-capture market
normalization and atomic acceptance. Use `LocalFileImporter` with the market
profile's `MAX_BYTES`, `S3RawPayloadStore`, explicit `MarketFixtureBinding` values
and a transaction factory yielding `PostgresMarketAcceptanceRepository`. Existing
source/venue/soccer event context must already match those bindings. The factory
must commit on clean exit and roll back on exceptions; use READ COMMITTED with
bounded statement/lock timeouts. No references are created implicitly.

The result contains the raw reference, accepted receipt IDs and newly inserted
receipt count (zero on exact retry). Every receipt is read back and compared before
commit; no success is returned if commit fails. Storage and complete normalization
precede the write transaction. Failure can leave reusable raw evidence without
canonical rows. There is no distributed S3/PostgreSQL transaction, publication,
automatic repair, production provider validation or research eligibility claim.

Read retained receipts through the repository, then call
`synthetic_markets.replay_market_fixture(store, candidates)` outside the database
transaction to verify complete retained raw/context reproduction. Missing/corrupt
raw fails replay; ordinary quote API reads do not imply fresh raw verification.
All observations stay `SYNTHETIC_ONLY`, with unknown availability preserved.

`scripts/test-integration -k market_fixture_raw_to_api` runs the complete authored
fixture workflow against disposable Floci/PostgreSQL resources and the real local
API composition. It verifies raw bytes, all three prices/provenance, concurrent
duplicate-free retries, retained-context replay and raw-loss/corruption failures.
`scripts/test-integration -k market_import_bad` checks that an invalid final outcome
is retained as raw but causes no write transaction or partial canonical effects.
See [ADR-034](../../../docs/adr/ADR-034-synthetic-market-quotes.md).

## The Odds API native parser

`odds_api_parser.parse_soccer_h2h(body, sport_key=..., snapshot_at=...)` validates
the complete bounded provider-shaped response before returning immutable native
staging values. It supports only decimal/ISO pre-match soccer h2h; no network,
canonical identity assignment, storage or mapping lookup occurs. Bookmaker and
market update timestamps remain separate and unknown values remain unknown.
Pass a documented capture instant (or explicitly simulated fixture instant), not
the current wall clock during replay. Parser output alone does not prove capture
origin, retention rights, regulation-time settlement or historical availability.

Run `uv run --locked --offline --all-packages pytest tests/unit/test_odds_api_parser.py`
for network-disabled coverage. Retained receipts and offline API composition follow
[ADR-035](../../../docs/adr/ADR-035-odds-api-soccer-adapter.md).

`odds_references.resolve_odds_references` resolves explicit source-scoped
competition, event and up to twenty bookmaker keys against existing mappings.
It returns immutable canonical event/HOME/AWAY context, source, sportsbook venues,
full selected revisions and a UTC cutoff. Missing, revoked, future, wrong-type,
inconsistent or collapsed references fail closed. It does not infer participant
identities from names, create references, or grant historical availability.

Use persistence `odds_references.odds_reference_reads(engine)` for one REPEATABLE
READ, read-only snapshot across a capture, with bounded SQL/idle waits. Complete
these reads before the acceptance transaction; do not perform raw storage I/O
inside the snapshot. Caller owns engine lifecycle and connection/pool timeouts.
Capture normalization composes these reads with the manifest. Whole-capture
receipts preserve the selected evidence through persistence and replay.

`odds_guards.OddsEventGuard` records explicit provider HOME/AWAY labels associated
with canonical participant IDs, a source-scoped event key and the expected kickoff.
`validate_odds_event_guard` compares parsed context against these guards and the
pinned references without repository reads. Labels must match exactly (not canonical
display names); participant roles, event/competition identity and all three kickoff
values must agree. Kickoff must be strictly after the supplied capture/fixture instant.
This pure guard does not establish rights, settlement semantics or historical
availability. Normalization retains it in whole-capture receipts.
Run `uv run --locked --offline --all-packages pytest tests/unit/test_odds_guards.py`
for its offline tests.

`odds_manifest.OddsCaptureManifest` binds the raw reference to an explicit v4
soccer h2h/decimal/ISO request with one to twenty requested bookmaker settlement
profiles. The raw resource must be exactly `/v4/sports/{sport_key}/odds`, without
query strings or credentials; arbitrary request parameters are not supported.
Each profile declares regulation-time semantics, a version, origin and SHA-256
reference to separately retained evidence. No real bookmaker profiles ship here.

Authored fixtures require `simulated_snapshot_at`, no `captured_at`, and derive
`SYNTHETIC_ONLY` usage. Provider captures require `captured_at <= ingested_at`, no
simulated clock, and an explicit rights-evidence digest; they derive `REPLAY_ONLY`.
Profiles must match capture origin, so fixture declarations cannot silently serve
as real settlement evidence. These are structural checks, **not rights approval**,
reviewer authentication or proof that the referenced evidence exists. Human review
of actual capture rights and settlement evidence remains required before use.
This bounded path requires unknown raw `available_at`; neither capture clocks nor
provider updates establish historical availability or backtest eligibility.

`read_odds_capture(store, manifest)` reads already-retained raw bytes once, verifies
size/hash, parses the entire response and rejects undeclared bookmakers. Run it
before reference/write transactions. Requested books may be absent, and empty
responses are valid: retain the manifest even when no native events are returned.
This is not canonical quote normalization, receipt serialization or acquisition.
Run `uv run --locked --offline --all-packages pytest tests/unit/test_odds_manifest.py`
for offline coverage; even the provider-origin branch tests use invented evidence.

`odds_normalization.normalize_odds_capture(store, manifest, guards, reads, as_of=...)`
verifies raw bytes before opening one caller-supplied reference snapshot for the
entire capture. Exact event guards and source-scoped competition/event/bookmaker
keys must cover the whole response; collapsed events, changed labels, missing
bookmaker mappings and inconsistent cutoffs fail without returning a partial batch.
Projection occurs after the snapshot closes. No canonical records are written.

The in-memory result retains the manifest, full selected reference evidence and
regulation-time three-way selections/quotes with exact Decimal prices. Known
market-level update times populate quote `observed_at`; bookmaker timestamps
are retained separately and never used as a market-level fallback. Raw capture
timestamps do not imply per-quote effective time or availability: both remain null.
Empty captures and no-quote events retain their evidence without invented prices.

Versioned observation IDs bind the complete manifest/raw identity and native
event/bookmaker/outcome, not derived prices or canonical mappings. A mapping
correction therefore changes the projection rather than silently allocating a
second observation for the same capture. Acceptance compares the full
projection on retry. Legacy synthetic identities/receipts are unchanged.
`replay_odds_capture(store, result)` re-reads raw bytes and compares the full
projection using only retained references, including after current mappings change
or are revoked. It is not a persistence command or authenticated evidence codec.
Run `uv run --locked --offline --all-packages pytest tests/unit/test_odds_normalization.py`.

`odds_receipts.encode_odds_receipt` / `decode_odds_receipt` provide a separate
whole-capture format 2 (maximum 8 MiB), including empty captures. Typed canonical
IDs, mapping revisions, manifests and quote projections use strict field/type
validation, exact decimal strings and canonical UTF-8-compatible ASCII JSON.
Unknown fields/versions, duplicate keys, noncanonical bytes, inconsistent quote
identities/membership/timestamps and excessive collections fail closed. This codec
does not change legacy market format 1. It validates structure/projection only;
`replay_odds_capture` must still verify prices against retained raw bytes before
the write transaction. No raw-store access occurs while decoding a receipt.
Run `uv run --locked --offline --all-packages pytest tests/unit/test_odds_receipts.py`.

Run `scripts/test-integration -k odds_reference` to check snapshot isolation,
concurrent revocation and transaction guards against disposable PostgreSQL.

### Offline Odds API import and retained replay

`odds_import.import_odds_capture(importer, store, manifest, guards, reads,
transactions, as_of=...)` composes the bounded offline path. Declare the expected
raw reference and reviewed context explicitly; the importer cannot silently replace
the manifest. Raw retention precedes parsing. One reference snapshot covers the
capture; normalization, receipt validation and raw replay finish before entering
the caller's write transaction. Acceptance/readback must match, and success returns
only after the context commits. Failed imports can leave raw evidence, but no
partially accepted quote prefix. Empty captures persist a receipt without prices.

Use `odds_reference_reads(engine)` for the PostgreSQL read composition. Supply a
write context yielding `PostgresOddsCaptureRepository` in READ COMMITTED with
bounded lock/statement timeouts, commit on clean exit and rollback on failure.
No public write endpoint, automatic migrations, live requests or event publication
are introduced. The complete executable composition is exercised in
`tests/integration/test_odds_import.py`.

For replay, fetch `repository.get(capture_id)` in a short database transaction,
close it, then call `replay_odds_capture(store, retained)` outside the transaction.
`accept_retained_odds_capture(store, retained, transactions)` additionally performs
an idempotent acceptance retry after verifying raw bytes, without current mapping
resolution. Fresh normalization after a mapping correction conflicts with the
original receipt; revoked mappings fail fresh resolution. Neither changes a
retained historical observation. API reads report stored evidence without claiming
fresh raw verification or current suitability.

Run `scripts/test-integration -k 'odds_fixture_raw_to_api or odds_import_empty'`
for authored Floci/PostgreSQL/API tests covering corrections, revocations, empty
captures, malformed responses and raw corruption. All evidence is invented;
provider capture rights/settlement review and historically eligible data remain
outside this goal. The legacy synthetic import path is unchanged.

## Sportmonks scheduled-fixture parser

Under [ADR-037](../../../docs/adr/ADR-037-sportmonks-fixture-adapter.md),
`sportmonks_parser.parse_scheduled_fixture(body, expected_fixture_id=..., snapshot_at=...)`
validates a bounded v3 single-fixture UTC response with participants/state includes.
It returns immutable provider-native staging values, not canonical event candidates.
Only soccer NS/non-placeholder fixtures are supported. Home/away comes from
`meta.location`, not array order or fixture name. UTC kickoff text must match the
integral Unix timestamp and follow the explicit aware snapshot instant.

Malformed fields, duplicate JSON keys, mismatched IDs, placeholder teams, unsupported
states/timezones and oversized inputs fail without side effects. Unknown additive
fields remain raw-only, including scores, xG, physical stadium IDs and processing
or subscription clocks. Native IDs never become canonical business IDs here.

The parser reads no files, environment, network or wall clock. A future composition
must retain/verify raw bytes first and pin capture origin and rights evidence;
successful parsing is not retention or historical availability. Canonical mappings,
receipt/storage compatibility, event correction and read-only consumer integration
remain subsequent increments. Existing synthetic/CSV/Odds API paths are unchanged.
See [authored fixture provenance](../../../tests/fixtures/providers/sportmonks/README.md).
Run `uv run --locked --offline --all-packages pytest tests/unit/test_sportmonks_parser.py`.
