# EdgeEagle API

Install from repository root with `scripts/bootstrap`. Start locally with:

```sh
uv run --locked --package edgeeagle-api uvicorn edgeeagle_api.main:app --host 127.0.0.1 --port 8000
```

`GET /health` returns `{"status":"ok"}` and indicates process liveness only.
It does not assert database, queue, model, or provider readiness. The application
starts without cloud/provider credentials or database configuration.

FastAPI exposes `/openapi.json` from the typed route definition. Root
`scripts/generate-contracts` exports its snapshot and TypeScript types;
`scripts/check-generated` checks drift without changing files. See
[contracts](../../contracts/README.md). Released-contract compatibility checks
remain pending.
The API reads canonical events through inward-owned ports; it owns no authoritative
business records. There are no authentication flows, provider adapters, or execution
capabilities. Bind locally for development;
production configuration and authentication require their own review.

## Private dataset contracts

`GET /v1/datasets` lists explicitly selected retained roots. The bounded list
reports `NOT_CHECKED`; `GET /v1/datasets/{rootHash}/inspection` freshly replays
one selected root and reports `VERIFIED` only on complete success. Neither permits
backtests. Both preserve private provenance and replay-only exclusions. The default
app returns 503 without accessing storage; malformed hashes return 422 and an
unselected root on a configured catalog returns 404. Storage loss/corruption returns
sanitized 503, never a partial success. Responses use `Cache-Control: no-store`.
See [ADR-032](../../docs/adr/ADR-032-local-dataset-api.md). There is no public hosting,
authentication decision, UI or MCP tool in this slice.

## Local event reads

`GET /v1/events` supports exact `sport_id`, `competition_id`, and `status` filters,
`limit` (1–100, default 50), and exclusive `after_event_id`. It returns `items` and
`next_after_event_id`; order is canonical ID, not event start time. Keep filters
unchanged while paging. `GET /v1/events/{eventId}` includes participant IDs/roles.
These are current-state reads, never historical backtest snapshots or predictions.
See [ADR-024](../../docs/adr/ADR-024-event-read-api.md).

The default app returns 503 for event reads without touching a database. To enable
them locally, start `scripts/local-up`, explicitly apply reviewed local migrations
with `scripts/migrate upgrade head`, and use:

```sh
EDGEEAGLE_DATABASE_URL=postgresql+psycopg://edgeeagle:edgeeagle-local@127.0.0.1:55432/edgeeagle \
uv run --locked --package edgeeagle-api uvicorn edgeeagle_api.local:create_local_app \
  --factory --host 127.0.0.1 --port 8000
```

The credentials above are disposable local Compose defaults. Override the port if
your local stack uses another port. No automatic seed/migration occurs; an empty
database returns an empty page. The factory accepts only explicit loopback
PostgreSQL/psycopg URLs without query options. Each request uses a read-only repeatable
snapshot; the bounded pool is disposed at shutdown. Database outages return sanitized
503 responses; schema/programming failures remain 500. Not production-ready or
authorized for public serving. Test with `scripts/test-integration -k event_api`.

Use root `scripts/format-check`, `scripts/lint`, `scripts/typecheck`,
`scripts/test-unit`, and `scripts/build`, or `scripts/validate` for all current checks.
Tests use the [FastAPI in-process test client](https://fastapi.tiangolo.com/tutorial/testing/).
pytest-socket blocks IP sockets; local Unix sockets remain available for the
event loop. Builds use the locked Hatchling installation without network access.

The [migration framework](migrations/README.md) establishes the local Alembic
baseline. It does not add domain tables or database access to the health endpoint.
