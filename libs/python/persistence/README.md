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

## Transaction ownership

The caller supplies an active PostgreSQL/psycopg SQLAlchemy connection transaction,
normally through `with engine.begin() as connection`. Autocommit is rejected.
Pass the same connection to both repositories to commit or roll back their work
together. The adapters never commit, roll back the outer transaction, close the
connection, create an engine, or read environment credentials.

Each `add` uses a savepoint so that a capability-insert failure also removes its
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
No paid provider or AWS credentials are used.

Root checks include this package; `scripts/build` regenerates its ignored sdist
and wheel under root `dist/`.
