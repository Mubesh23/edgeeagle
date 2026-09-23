# Local Football-Data results import workflow

## What is implemented

A reusable Python application operation, not a downloader, CLI, API endpoint, or
hosted job: `edgeeagle_ingestion.football_data_import.import_results_dataset`.
The supported CSV subset and identity/time rules are fixed by
[ADR-028](../adr/ADR-028-football-data-results-import.md).

```text
Trusted local CSV
  -> unchanged raw bytes + capture metadata in S3/Floci
  -> complete validation + pinned mapping/reference reads
  -> one PostgreSQL transaction: events + immutable format-3 receipts
  -> canonical replay-only manifest in S3/Floci
  -> retrieve by dataset version -> verify against retained raw and receipt context
```

The score is retained inside each immutable receipt, not a new settlement table or
an API result field. Extra CSV columns, including odds/statistics, remain raw-only.
This workflow does not create notifications; legacy publication-aware acceptance
remains a separate capability. No Parquet/model/backtest readiness is claimed.

## Run the complete local evidence

From repository root, with Docker running and dependencies bootstrapped:

```sh
scripts/test-unit tests/unit/test_football_data.py tests/unit/test_soccer_receipts.py tests/unit/test_football_data_manifest.py tests/unit/test_football_data_import.py
scripts/test-integration -k football_data_import
scripts/validate
```

The integration command creates/migrates disposable PostgreSQL databases and Floci
buckets. It imports the committed authored CSV, performs sequential/concurrent
reimports, retrieves and replays its snapshot after mapping revocation/reference
edits, and tests raw loss/corruption. It also tests final-row conflict rollback,
malformed final-row retention without canonical effects, and manifest-storage
failure after database commit. Only test-owned resources are removed afterward;
local services stay running. This test demonstrates the workflow but intentionally
does not leave its temporary dataset in the developer database.

## Application prerequisites

For caller-managed persistent use, supply:

- A trusted local file and permission to retain/use it. Real provider files need
  rights review; nothing is downloaded by this operation. The committed fixture
  is wholly synthetic and must not be registered as a real provider capture.
- An explicit `RawCapture` with the registered source ID, resource (include the
  competition/season acquisition scope), and original ingestion timestamp. Leave
  unknown effective/observed/available timestamps None. The actual source should
  be registered as an OFFLINE_DATASET, not a Venue.
- Preexisting canonical sport (`soccer`), competition, season, TEAM participants,
  and reviewed mappings for the five reference roles. No fuzzy matching or mapping
  writes occur here. Use the actual source scope for real files, synthetic for tests.
- A `FootballDataRequest` for every CSV row, with a stable internally allocated
  event ID, source-scoped `row_locator`, exact division/home/away guards, five
  reference keys, explicit context version, and a confirmed UTC offset for that
  row's local kickoff. Preserve the same requests and capture metadata on retry.
- An explicit aware resolution cutoff, not an inferred historical knowledge time.
- An S3 client/bucket and PostgreSQL engine whose lifecycle/timeouts you own.
  Local clients use loopback Floci and explicit dummy credentials. Apply migrations
  through `scripts/migrate` explicitly when choosing to use your developer database;
  tests never do this for you.

Compose `LocalFileImporter(path, capture, max_bytes=MAX_CSV_BYTES)`,
`S3RawPayloadStore(client, bucket)`, `fixture_reference_reads(engine)`,
`EventReceiptCodec()`, and `S3ReplayManifestStore(client, bucket, codec)`.
The acceptance transaction factory must commit only on clean exit and roll back
the entire batch on error. For PostgreSQL it has this shape:

```python
from contextlib import contextmanager
from edgeeagle_persistence.events import PostgresEventAcceptanceRepository


@contextmanager
def transactions():
    with engine.begin() as connection:
        yield PostgresEventAcceptanceRepository(connection)
```

Configure finite connection/pool/statement/lock timeouts for your engine. Then call
`import_results_dataset(importer, raw_store, requests, reads, transactions,
manifest_store, codec, as_of=cutoff)` to obtain the dataset version. Retain this
returned version; no catalog or mutable latest alias is provided. Retrieve with
`manifest_store.get(version)`, explicitly handle None, then call
`verify_manifest(body, codec, raw_store)` when artifact verification is required.
No current database reader is needed for that replay.

## Failure and retry semantics

### Whole-season profile

For complete captures of up to 512 rows (still at most 1 MiB of raw CSV), use
`edgeeagle_ingestion.football_data_season_import.import_season_dataset` with
`S3SeasonObjectStore(client, bucket, codec)` instead of the legacy operation/store.
Arguments and reference/transaction prerequisites are otherwise the same. No
automatic promotion of legacy receipts occurs. See
[ADR-029](../adr/ADR-029-football-data-season-replay.md).

The whole batch is accepted/read back in one PostgreSQL transaction, including
all page/root encoding and size checks. After commit, the operation writes all
pages (up to 64 receipts each) first, then the root, validating every returned object hash.
It returns the root hash only after the final acknowledgement:

```python
root_hash = import_season_dataset(
    importer, raw_store, requests, reads, transactions, object_store, codec, as_of=cutoff
)
body = object_store.get(root_hash)
if body is None:
    raise FileNotFoundError("Retained season root is missing")
results = verify_bundle(body, codec, object_store, raw_store)
```

Import `verify_bundle` from `edgeeagle_ingestion.season_bundle` and the store from
`edgeeagle_persistence.season_storage`. Verification reads no current database
state. A missing final page fails the complete replay, even if the root survives.
Storage validates individual objects, not complete season membership.

Failure after PostgreSQL commit can leave receipts and a prefix of pages without
a root; they are not rolled back. Retry the exact capture/requests/context with
unchanged references. If references changed, caller-controlled reconstruction
must use immutable accepted receipts with `build_bundle`, not new normalization.
Ambiguous storage acknowledgements can leave a complete bundle even when the call
raises; exact conditional retry remains safe. No root hash is returned on failure.

Run `scripts/test-unit tests/unit/test_season_import.py tests/unit/test_season_storage.py`
and `scripts/test-integration -k 'season_import or season_storage'`.
Routine tests use authored rows and disposable resources, not the downloaded EPL
file. The real import still requires reviewed canonical mappings and confirmed
kickoff offsets. Historical availability stays unknown and usage stays REPLAY_ONLY.

### Shared failure rules

- Invalid parsing/context: raw bytes remain; no acceptance transaction begins.
- Any acceptance/readback/manifest-size failure: the entire acceptance transaction
  rolls back. Earlier raw retention is independent and remains reusable.
- Commit error: no manifest write is attempted. An ambiguous commit requires an
  exact retry/receipt inspection; no automatic compensating delete is attempted.
- Manifest write error after commit: accepted receipts remain. Retrying identical
  input/context with unchanged references is a no-op in PostgreSQL and can finish
  manifest storage. If references changed, retrieve the immutable accepted receipts
  and rebuild/verify their manifest; do not renormalize against new state and call
  it the original import. That recovery is caller-controlled, not automatic.
- Changed results/context for an existing event conflict. This initial-insert
  workflow does not silently correct or refresh accepted history.
- Lost manifest returns absence; lost/corrupt raw data fails replay. Neither path
  fetches replacement provider data or reconstructs from current canonical tables.

Conditional writes and append-only receipts prevent accidental application
overwrites; they are not backups, authenticated provenance, production IAM or
Object Lock. Local volumes can still be deleted by an operator. All snapshots
remain `REPLAY_ONLY`: unknown availability and caller-asserted context cannot
be promoted into historical decision-time evidence.
