# Python domain library

`edgeeagle-domain` implements the inward dependency boundary described by the
[TDD](../../../docs/architecture/TDD.md). It has no runtime dependencies and does
not import FastAPI, database clients, AWS SDKs, or provider schemas.

The first Phase 2 slice implements `DataSource`, `Venue`, their distinct ID
value types, and the source/venue categories from the
[canonical model](../../../docs/architecture/canonical-domain-model.md).
Provider names are data, not domain enums. An aggregator and a sportsbook remain
independent records; an operator such as Kalshi may have both roles.

The next slice adds `Sport`, `Competition`, `Season`, `Participant`, `Event`,
and `EventParticipant` in `edgeeagle_domain.sports`, with separate ID value types.
Event participants are independent association records: no two-team restriction,
home/away requirement, or globally unique role is imposed. Competition metadata
can preserve gender/division, and event location is not a market `Venue`.

Schedule times must be timezone-aware datetimes; input offsets are retained.
Season end cannot precede its start when compared as UTC instants (including DST
folds); equal endpoints are allowed. These records are not historical snapshots:
schedule times do not establish `available_at` or backtest eligibility.

The draft model does not define a closed event-status vocabulary, complete
participant/role taxonomies, or lifecycle transitions. These fields currently
accept nonblank, unpadded text, not provider enums or authoritative state-machine
rules. Future versioned normalizers must define canonical labels and reject or
quarantine unmapped provider values before ingestion uses these records. No
adapter is implemented or implied by accepting a label here.

Constructors validate individual record structure only. The separate pure
`edgeeagle_domain.consistency.validate_event_context` checks a supplied event,
sport, competition, season, participants, and event entries for relationship
consistency. It rejects mismatched references, cross-sport participants,
duplicate participant records, missing references, duplicate entries (even with
different roles), and unattached participant records. Supply exactly the
participants associated with the event, not a global participant catalog.

This explicit resolved-context check requires at least one entry. Incomplete
events can still be represented by individual records; passing this check does
not prove the roster is complete for a particular sport. Repeated roles such as
`FIELD` and any positive participant count are allowed. Season date containment,
status transitions, and sport-specific rules are not inferred. Validation returns
`None` or raises `ValueError` for inconsistency / `TypeError` for wrong input
types; it does not mutate, resolve names, query stores, or persist quarantine
records. Future ingestion callers must handle failures before writing canonical
state. Persisted reference existence, concurrency, rescheduling history, and
historical availability still need application/persistence validation.

Provider mappings remain unimplemented. The conceptual fields require an
auditable/versioned design, but revision identity, supersession, confidence scale,
and mapping approval rules have not yet been specified. Those decisions must be
documented before mapping records are used for canonical resolution.

These internal records use frozen standard-library dataclasses. Constructors
reject wrong types, blank text, surrounding whitespace, and mutable capability
collections; they do not silently normalize provider input. Adapters will own
that transformation. Empty capability sets are valid and confer no permissions.
Capabilities are descriptive string tags, not execution or authorization policy;
the controlled vocabulary remains deferred until adapters require it.

IDs wrap opaque strings and are distinct at runtime and under static typing.
They do not choose UUID/ULID encoding, generate IDs, establish uniqueness, or
prove that an ID was internally allocated. Future persistence/application code
must allocate stable canonical IDs and store provider IDs in explicit mappings.
No provider catalog, real jurisdiction/licensing assertion, persistence mapping,
external serialization contract, or API endpoint is introduced here.

Run from the repository root:

```sh
scripts/bootstrap
uv run --locked --offline --all-packages pytest libs/python/domain/tests
uv run --locked --offline --all-packages pytest libs/python/domain/tests --cov=edgeeagle_domain --cov-branch --cov-report=term-missing
scripts/typecheck
scripts/build
scripts/validate
```

Root format/lint/typecheck/unit checks include this package; build creates its
ignored sdist and wheel under root `dist/`. Unit tests disable network sockets.
