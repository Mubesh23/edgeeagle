# ADR-033 — Private local dataset browser

**Status:** Accepted for implementation
**Date:** 2026-09-23

## Decision

Add a read-only retained-dataset panel to the existing web shell. Use the
generated API client and ADR-032's approved same-origin loopback Vite proxy;
no API, CORS, authentication, networking or hosting changes are needed.

Load bounded catalog metadata on mount and on explicit refresh. Show full root
identity, operator annotation, declared counts, raw provenance and version pins.
Unknown timestamps remain visibly unknown. Listing is always `NOT_CHECKED`.
An explicit per-root action requests fresh backend replay inspection. Never
inspect automatically, poll, retry automatically or compute eligibility locally.

Render backend receipt/participant counts, completion time, asserted kickoff range,
scope IDs and context versions only after a successful inspection. Label this as
an observation at that time, not durable verification. Hide previous success while
checking again or after failure. Cancel requests when a view unmounts, use bounded
client timeouts and discard inactive query data. No browser persistence, exports,
provider calls, raw downloads or data writes are introduced. Cancellation stops
browser waiting, not necessarily synchronous backend work already in progress.

Both listing and inspection retain visible replay-only and not-backtest-eligible
warnings. Explain that replay does not verify rights, database acceptance or
kickoff accuracy. Runtime response checks fail closed on malformed data, mismatched
root identity or incompatible eligibility/status fields; they do not recalculate
backend judgments. Render labels as text and never display raw error payloads.

## Validation

Authored synthetic component/transport tests cover loading, empty/unavailable
catalogs, manual refresh, explicit inspection, failure after success, cancellation,
identity/eligibility rejection and visible provenance/limitations. Use generated
types, lint, typecheck, build and full root validation. Private captures remain
outside fixtures, source bundles and hosted CI. A local browser remains private
research only; this does not authorize external exposure or model/backtest use.
