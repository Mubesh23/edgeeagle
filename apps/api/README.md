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
There are no authoritative business records, authentication flows, provider
adapters, or execution capabilities in this shell. Bind locally for development;
production configuration and authentication require their own review.

Use root `scripts/format-check`, `scripts/lint`, `scripts/typecheck`,
`scripts/test-unit`, and `scripts/build`, or `scripts/validate` for all current checks.
Tests use the [FastAPI in-process test client](https://fastapi.tiangolo.com/tutorial/testing/).
pytest-socket blocks IP sockets; local Unix sockets remain available for the
event loop. Builds use the locked Hatchling installation without network access.

The [migration framework](migrations/README.md) establishes the local Alembic
baseline. It does not add domain tables or database access to the health endpoint.
