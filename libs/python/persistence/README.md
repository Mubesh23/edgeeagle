# PostgreSQL persistence adapters

`edgeeagle-persistence` depends inward on `edgeeagle-domain` and implements its
repository protocols using SQLAlchemy connections and the psycopg driver.
Importing the package opens no database connection. The API has no dependency on
this package yet; no endpoint, deployment, database configuration, or schema
migration is introduced by these adapters.

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
list, historical/as-of, entity-resolution, or provider-mapping operations yet.

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

## Caller-owned transactions

The caller supplies an active PostgreSQL/psycopg SQLAlchemy connection transaction,
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
No paid provider or AWS credentials are used.

Root checks include this package; `scripts/build` regenerates its ignored sdist
and wheel under root `dist/`.
