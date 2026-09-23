# Database migrations

Run from repository root after `scripts/bootstrap` and `scripts/local-up`:

```sh
scripts/migrate                 # upgrade the local database to head
scripts/migrate current
scripts/migrate history
scripts/migrate upgrade head --sql
```

The wrapper always targets Compose's loopback database `edgeeagle`, using the
local credentials and `EDGEEAGLE_POSTGRES_PORT` (default 55432). It overrides any
inherited `EDGEEAGLE_DATABASE_URL`. It does not start services or perform a
downgrade implicitly. Neither the API startup nor local-up applies migrations.
Direct Alembic use requires an explicit URL or an injected SQLAlchemy connection;
deployment/migration automation is not included in this foundation.

Revision `0001_foundation` establishes Alembic's version ledger only and remains
unchanged. Revision `0002_source_venue` adds the first canonical storage tables:

- `data_sources`: opaque text ID, code, documented source category.
- `venues`: separate opaque text ID, operator, product, jurisdiction, venue category.
- `data_source_capabilities` and `venue_capabilities`: one row per capability,
  with composite primary keys implementing set uniqueness and indexed parent FKs.

Source and venue IDs occupy independent namespaces, even for the same operator.
IDs/capabilities use deterministic `C` collation; callers allocate stable IDs.
No provider IDs are promoted, catalogs seeded, or ID-generation scheme selected.
An empty capability set is represented by no child rows. Capability tags are
descriptive metadata, not authorization. Foreign keys restrict parent deletion
and ID updates; no cascade silently removes capability rows.

Named checks reject unknown categories and empty/edge-whitespace text under
PostgreSQL's whitespace rules. Domain constructors remain authoritative for
Python's full Unicode whitespace validation. Categories are frozen in this
revision rather than imported from evolving domain enums. Future additions must
use a new migration. Codes/operator labels are not asserted globally unique.

This is a schema-only increment, not a runtime repository or an HTTP ownership
boundary: API startup still owns no business data or database connection.
Sports/event tables, mapping history, repository adapters, and seed workflows
remain later increments. Revisions own explicit DDL; ORM metadata and migration
autogeneration are not enabled.

An explicit downgrade below `0002_source_venue` drops these four tables and their
data. Do not downgrade populated application databases without human review and
a recovery plan. Automated tests perform this only in disposable databases.

Use `scripts/migrate revision -m 'describe the schema change'` to create the next
revision, implement its upgrade/downgrade, and review the SQL. Apply Ruff to new
revision files. Never rewrite an applied revision. Breaking changes require
human review; database resets are not part of normal validation.

Unit tests check the single migration head and offline SQL generation with
network disabled. Integration tests create a uniquely named temporary database,
upgrade from the foundation, repeat the upgrade, verify committed state and
PostgreSQL constraints, downgrade to base, and reapply head. An unrelated sentinel
table proves the migration does not remove tables it does not own. They
dispose connections and delete only that temporary database. The developer's
`edgeeagle` database is not downgraded or reset by tests.

Migrations and alembic.ini are checkout-managed deployment assets, not included
in the API wheel. Packaging deployment assets will be addressed when deployment
is introduced. The API remains independent of database connectivity at startup.
