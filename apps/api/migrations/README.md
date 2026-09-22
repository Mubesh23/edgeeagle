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

Revision `0001_foundation` establishes Alembic's version ledger only. It creates
no domain tables. Phase 2 introduces canonical models and migrations; metadata
is intentionally absent until then, so autogeneration is not yet supported.

Use `scripts/migrate revision -m 'describe the schema change'` to create the next
revision, implement its upgrade/downgrade, and review the SQL. Apply Ruff to new
revision files. Never rewrite an applied revision. Breaking changes require
human review; database resets are not part of normal validation.

Unit tests check the single migration head and offline SQL generation with
network disabled. Integration tests create a uniquely named temporary database,
upgrade twice, verify committed state, downgrade to base, and reapply head. They
dispose connections and delete only that temporary database. The developer's
`edgeeagle` database is not downgraded or reset by tests.

Migrations and alembic.ini are checkout-managed deployment assets, not included
in the API wheel. Packaging deployment assets will be addressed when deployment
is introduced. The API remains independent of database connectivity at startup.
