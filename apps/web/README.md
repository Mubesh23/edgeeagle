# Web foundation

React/TypeScript/Vite shell using TanStack Query and the generated
`@edgeeagle/api-client`. It displays API process liveness only. No market data,
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

The browser uses same-origin `/api/health`. Requests have a five-second timeout,
consume TanStack's cancellation signal, and do not poll or retry automatically.
The user can explicitly check again. A successful response does not assert
database, model, or provider readiness. Errors never display raw server payloads.

Root format/lint/typecheck/test/build/validate commands include this package.
Tests use jsdom with injected transports and a rejecting global fetch fallback;
they exercise loading, success, invalid payloads, failure, and manual retry.
These are component/transport tests, not real-browser E2E tests.

`scripts/build` generates ignored `apps/web/dist/` from index.html, src/, and
Vite configuration. Production hosting is not implemented: it must route
`/api/*` to the backend with the same prefix rewrite. Vite's development proxy
is not part of the static build. Do not deploy this unauthenticated shell as a
production terminal. No secrets belong in client source or Vite variables.

Tool references: [Vite](https://vite.dev/guide/) and
[TanStack cancellation](https://tanstack.com/query/latest/docs/framework/react/guides/query-cancellation).
