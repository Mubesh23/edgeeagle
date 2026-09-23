# Python domain library

`edgeeagle-domain` implements the inward dependency boundary described by the
[TDD](../../../docs/architecture/TDD.md). It has no runtime dependencies and does
not import FastAPI, database clients, AWS SDKs, or provider schemas.

The first Phase 2 slice implements only `DataSource`, `Venue`, their distinct ID
value types, and the source/venue categories from the
[canonical model](../../../docs/architecture/canonical-domain-model.md).
Provider names are data, not domain enums. An aggregator and a sportsbook remain
independent records; an operator such as Kalshi may have both roles.

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
scripts/typecheck
scripts/build
scripts/validate
```

Root format/lint/typecheck/unit checks include this package; build creates its
ignored sdist and wheel under root `dist/`. Unit tests disable network sockets.
