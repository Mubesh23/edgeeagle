# Web foundation

React/TypeScript/Vite shell using TanStack Query and the generated
`@edgeeagle/api-client`. It displays API process liveness and a private retained
dataset browser. No market data,
domain calculations, authentication, or trading workflows are implemented.
Router/Table packages await actual routes and tabular features.

From repository root, run `scripts/bootstrap` and `scripts/build` once, then
start the API and web in separate terminals:

```sh
uv run --locked --offline --all-packages uvicorn edgeeagle_api.main:app --host 127.0.0.1 --port 8000
corepack pnpm --filter @edgeeagle/web dev
```

Open http://127.0.0.1:5173. Vite binds only to loopback, uses a strict port, and
proxies `/api/*` to the local API at port 8000, stripping the `/api` prefix.
No backend CORS change or browser provider credentials are needed.

This existing loopback-only development proxy is permitted for the private
dataset API under [ADR-032](../../docs/adr/ADR-032-local-dataset-api.md).
Keep both servers bound to 127.0.0.1; do not expose them to the LAN or internet
through another proxy, tunnel or hosted deployment. This is not authentication
and does not change dataset rights or replay-only eligibility.

## Private dataset browser

Start Floci with `scripts/local-up`, then enable the opt-in catalog API instead
of the default health-only configuration:

```sh
EDGEEAGLE_DATASET_CATALOG=.data/dataset-catalog.json \
uv run --locked --offline --package edgeeagle-api uvicorn \
  edgeeagle_api.local_datasets:create_local_dataset_app \
  --factory --host 127.0.0.1 --port 8000 --no-proxy-headers
corepack pnpm --filter @edgeeagle/web dev
```

Run the API and web commands in separate terminals. Configure selected roots using
the [catalog guide](../../docs/development/dataset-catalog.md); no dataset or
private configuration is bundled into the web app. An unconfigured API shows an
unavailable state; an empty selected catalog shows an empty state, not sample data.

The panel lists root identities, declared counts, operator annotations, provenance,
version pins and backend exclusion reasons. Listing does not verify replay.
Select **Inspect replay** to request a fresh backend inspection, with completion
time, verified counts, asserted kickoff range and retained canonical scope/context.
It does not verify rights, database acceptance or kickoff accuracy. Every result
remains replay-only and not backtest-eligible. See
[ADR-033](../../docs/adr/ADR-033-private-dataset-browser.md).

Requests use no-store, cancellation and 15-second list/60-second inspection
timeouts. No polling, automatic replay/retries or focus/reconnect refetch occurs.
Previous replay success is hidden during a new check and after failure. Catalog
refresh clears displayed inspections; inactive query data is discarded and nothing
is persisted to browser storage. Cancellation stops browser waiting but may not
stop synchronous backend work already in progress. Errors display no raw payloads.

## Liveness and validation

The browser uses same-origin `/api/health`. Requests have a five-second timeout,
consume TanStack's cancellation signal, and do not poll or retry automatically.
The user can explicitly check again. A successful response does not assert
database, model, or provider readiness. Errors never display raw server payloads.

Root format/lint/typecheck/test/build/validate commands include this package.
Tests use jsdom with injected transports and a rejecting global fetch fallback;
they exercise loading, success, invalid payloads, failure, and manual retry.
Catalog tests additionally cover explicit replay, provenance/eligibility warnings,
identity mismatch, prior-success invalidation, refresh, empty states, cancellation
and safe text rendering. All test data is authored synthetic data.
These are component/transport tests, not real-browser E2E tests.

`scripts/build` generates ignored `apps/web/dist/` from index.html, src/, and
Vite configuration. Production hosting is not implemented: it must route
`/api/*` to the backend with the same prefix rewrite. Vite's development proxy
is not part of the static build. Do not deploy this unauthenticated shell as a
production terminal. No secrets belong in client source or Vite variables.

Tool references: [Vite](https://vite.dev/guide/) and
[TanStack cancellation](https://tanstack.com/query/latest/docs/framework/react/guides/query-cancellation).
