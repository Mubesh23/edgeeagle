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

## Real Chromium checks from the CLI

Install the pinned browser once after bootstrap (public browser binaries, not
provider data), then run the separate browser tier:

```sh
corepack pnpm --filter @edgeeagle/web exec playwright install chromium
scripts/test-browser
```

On Linux, browser OS dependencies may require Playwright's
`install --with-deps chromium` setup. Browser installation is explicit, not part
of bootstrap, unit tests or `scripts/validate`. Run both `scripts/validate` and
`scripts/test-browser` for browser-flow changes. Hosted CI installs Chromium with
Linux dependencies and runs this additional tier after foundation validation;
either step failing fails the job. See [CI policy](../../docs/development/ci.md).

The command builds the client/web and starts a dedicated static preview on
127.0.0.1:4173 without an API proxy. It refuses to reuse an occupied port.
Tests intercept API requests with authored fixtures, reject unexpected page
requests, block service workers and use isolated Chromium contexts. No API,
database, Floci, private catalog, desktop bridge or paid provider is required.
Playwright shuts down its owned preview server after the run.

Desktop (1280×900) and narrow (390×844) checks cover provenance, explicit replay,
success followed by failure, unavailable/empty states, invalid eligibility and
horizontal overflow. Success screenshots and failure artifacts are generated
under ignored `apps/web/test-results/`; the ignored HTML report is under
`apps/web/playwright-report/`. Regenerate with `scripts/test-browser`. Screenshots
are inspection evidence, not committed pixel-diff baselines or a full accessibility
audit. Narrow Chromium is not a native mobile or Safari test.

References: [Playwright server lifecycle](https://playwright.dev/docs/test-webserver)
and [request interception](https://playwright.dev/docs/network).

CLI browser evidence (2026-09-23): `scripts/test-browser` passed all four Chromium
checks (two scenarios at both widths). Both generated success screenshots were
visually inspected: provenance and replay-only warnings are readable, narrow
content wraps, and the replay observation is distinct from metadata. No horizontal
overflow or page JavaScript errors were observed in the successful replay checks.
This closes the earlier desktop-bridge visual-check gap for these synthetic
Chromium scenarios, not for every browser or the live private-data workflow.
Full `scripts/validate` passed after adding Playwright: 875 Python unit tests,
141 integration tests plus the existing Floci expected failure, 24 web component
tests, contract checks, lint/typing/formatting, builds, synthesis and advisory
scans. Unchanged tasks reused local Turbo cache. No known advisories were reported.
Hosted CI, a fresh checkout, Firefox and WebKit were not exercised in this session.

## Earlier local validation evidence

Local validation evidence (2026-09-23): all 24 web tests, lint, typing and build
passed. A temporary loopback Vite/API smoke test served the app and exercised the
generated client's catalog list/inspection through `/api`, returning 380 receipts
and 20 participants from the retained season with backtest eligibility still false.
Both temporary app servers were stopped afterward. This verifies HTTP/proxy
composition, not browser rendering. Visual verification was attempted using the
Browser skill, but its native connection was unavailable before session setup;
no screenshot or real-browser interaction result is claimed.

Full `scripts/validate` also passed: 875 Python unit tests, 141 integration tests,
the existing one Floci expected failure, generated drift/compatibility checks,
formatting, lint, typing, builds, credential-free synthesis and advisory scans.
Changed web tasks ran; unchanged packages reused local Turbo cache. Existing
Starlette deprecations and the resource-free CDK warning remain. Hosted CI and
fresh-checkout validation were not run in this local session.

`scripts/build` generates ignored `apps/web/dist/` from index.html, src/, and
Vite configuration. Production hosting is not implemented: it must route
`/api/*` to the backend with the same prefix rewrite. Vite's development proxy
is not part of the static build. Do not deploy this unauthenticated shell as a
production terminal. No secrets belong in client source or Vite variables.

Tool references: [Vite](https://vite.dev/guide/) and
[TanStack cancellation](https://tanstack.com/query/latest/docs/framework/react/guides/query-cancellation).
