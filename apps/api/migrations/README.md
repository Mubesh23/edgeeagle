# Database migrations

Revision `0008_event_consumption` adds immutable verification receipts for the
first EventAccepted consumer, keyed by notification ID. Downgrade removes these
receipts and permits reprocessing; it is not an operational reset. Existing
canonical data/outbox intents are preserved. Only disposable databases are migrated
by validation. See [ADR-023](../../../docs/adr/ADR-023-event-acceptance-consumer.md).

Revision `0007_outbox_delivery` adds mutable delivery state, eligibility indexes,
and an AFTER INSERT trigger that initializes state atomically with each outbox
intent. Existing intents receive pending operational state without envelope edits.
Downgrade preserves intents but discards delivery state: once external publication
exists, downgrade/reupgrade risks redelivery and requires human review. See
[ADR-020](../../../docs/adr/ADR-020-outbox-delivery-leases.md).

Revision `0006_event_outbox` adds immutable pending notification envelopes linked
to accepted normalization receipts. It does not backfill old receipts or change
their timestamps. Downgrade removes only the outbox table/function. See
[ADR-019](../../../docs/adr/ADR-019-event-outbox.md). Delivery state and relay
execution are not implemented by this migration.

Revision `0005_event_acceptance` adds immutable `event_normalizations` receipts
with event/source foreign keys and a versioned JSONB accepted-output snapshot.
Its downgrade removes only that table and its immutability function. See
[ADR-018](../../../docs/adr/ADR-018-event-acceptance-lineage.md). The application
database is not migrated automatically; integration tests use disposable databases.

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

Revision `0003_sports_events` adds `sports`, `competitions`, `seasons`,
`participants`, `events`, and `event_participants`. It retains opaque text IDs
and the same text guards. Optional gender/division and venue-location fields may
be NULL; supplied labels cannot be blank. Status, participant-type, and role
labels remain extensible; no provider taxonomy or lifecycle policy is invented.

Composite foreign keys enforce event/competition sport agreement and
event/season competition agreement. The storage-only `event_participants.sport_id`
must match **both** its event and participant through composite foreign keys.
This redundant column enables database enforcement without triggers; it does not
add a field to the canonical domain `EventParticipant` or change public contracts.
Repositories must derive it from the validated context, not accept a conflicting
caller value. Supporting unique constraints and referencing-side indexes are
explicit. Restrictive updates/deletes prevent silently breaking existing links.

The `(event_id, participant_id)` primary key prevents duplicate event entries,
even under different roles. Repeated roles and any participant count are allowed;
empty/partial events remain representable until the domain's resolved-context
validation runs. Role validity and roster completeness remain application rules.

Schedule columns use finite `timestamptz` instants; season end must not precede
start. Events may fall outside season dates (for example, rescheduling). PostgreSQL
does not retain the original timezone/offset and may interpret naive SQL input
using the session timezone: future adapters must still reject naive datetimes
through the domain constructors. Current-state tables are not historical datasets
and do not establish `available_at`, snapshot versions, or backtest eligibility.

Revision `0004_mapping_history` adds `provider_mapping_keys` and
`provider_mapping_revisions` as defined by
[ADR-014](../../../docs/adr/ADR-014-provider-mapping-storage.md). Keys retain opaque,
case-sensitive source/type/provider-ID namespaces and a fixed target kind.
Six nullable typed target FKs, an exactly-one-target check, and a composite key FK
enforce canonical existence and stable target type. A generated predecessor
revision/self-FK enforces contiguous revision numbers starting at 1; the first
revision must be MAPPED. Numeric confidence has no declared rounding scale and
must be NULL or within [0, 1]. Decision timestamps are finite, ordered timestamptz
instants. PostgreSQL representation limits still apply.

Statement triggers reject UPDATE, DELETE, and TRUNCATE on the two mapping tables.
This prevents accidental mutation, not a privileged owner disabling triggers.
There are no role/grant or authentication changes. The mapping repository now
locks keys, reuses complete-history validation, accepts the next proposed revision,
and handles exact replay. Inter-revision timestamp ordering and revocation target
retention are enforced by that repository, not this schema alone. No ingestion
or API mapping write path is wired yet.

These are schema-only increments, not a runtime repository or an HTTP ownership
boundary: API startup still owns no business data or database connection.
Source/venue, sports/event, and mapping repository adapters now live in the separate
[persistence package](../../../libs/python/persistence/README.md), using caller-owned
transactions. Ingestion/seed workflows remain later increments.
Revisions own explicit DDL; ORM metadata and migration
autogeneration are not enabled.

An explicit downgrade from `0003_sports_events` drops its six sports tables and
their data, leaving the source/venue tables intact.
An explicit downgrade below `0002_source_venue` drops these four tables and their
data. Do not downgrade populated application databases without human review and
a recovery plan. Automated tests perform this only in disposable databases.

Downgrading `0004_mapping_history` to `0003_sports_events` removes the two mapping
tables (and their data/triggers) plus the mapping trigger function, preserving
prior canonical tables. Tests verify this with seeded records and reapply head.

Use `scripts/migrate revision -m 'describe the schema change'` to create the next
revision, implement its upgrade/downgrade, and review the SQL. Apply Ruff to new
revision files. Never rewrite an applied revision. Breaking changes require
human review; database resets are not part of normal validation.

Unit tests check the single migration head and offline SQL generation with
network disabled. Integration tests create a uniquely named temporary database,
upgrade from the foundation, repeat the upgrade, verify committed state and
PostgreSQL constraints and FK indexes, downgrade to the source/venue revision
and reapply, then downgrade to base and reapply head. An unrelated sentinel
table proves the migration does not remove tables it does not own. They
dispose connections and delete only that temporary database. The developer's
`edgeeagle` database is not downgraded or reset by tests.

Migrations and alembic.ini are checkout-managed deployment assets, not included
in the API wheel. Packaging deployment assets will be addressed when deployment
is introduced. The API remains independent of database connectivity at startup.
