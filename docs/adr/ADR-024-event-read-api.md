# ADR-024 — Current-state event reads

**Status:** Accepted for local Phase 2 implementation  
**Date:** 2026-09-23

## Decision

Expose the planned `GET /v1/events` and `GET /v1/events/{eventId}` using
canonical PostgreSQL records. The API owns serialization and request validation,
not authoritative event data. Domain owns a read-only event query port;
persistence implements it. No new deployable, projection, migration, or provider
call is required. Consumer verification receipts do not gate current-state reads:
canonical acceptance is already committed before publication.

List filters are optional exact `sport_id`, `competition_id`, and `status`.
Pagination uses `limit` (default 50, range 1–100) and `after_event_id` (exclusive).
Results sort by canonical event ID using PostgreSQL C collation, not start time
or sporting rank. Return `{items: Event[], next_after_event_id: string | null}`,
fetching one extra row to determine continuation. Clients retain the same filters
across pages. This is current-state pagination, not a frozen multi-request snapshot;
concurrent insertions before the cursor and changed filter membership can be missed.
No total count, arbitrary sort, fuzzy search, or historical `as_of` is promised.

Event fields are the canonical model's seven fields with IDs serialized as strings
and timezone-aware `starts_at`. Detail adds `participants`, containing canonical
participant ID and role, ordered by participant ID. Roles/status remain validated
strings, not invented closed enums. Detail is read in one REPEATABLE READ, READ ONLY
transaction. List queries are bounded and parameterized. Reads cannot mutate data.

Missing event returns 404; malformed query/path input returns 422; unconfigured or
unavailable database returns a sanitized 503. Missing database tables/programming
errors remain server failures, not empty successful results. No SQL/credentials in
HTTP error payloads. `/health` remains database-independent liveness.

The default application stays credential-free and has no configured event reader.
A separate explicit local factory accepts a loopback PostgreSQL/psycopg URL from
`EDGEEAGLE_DATABASE_URL`, with bounded pool, connection, and statement timeouts.
Its lifespan owns/disposes the engine; requests own read transactions. Bind the
development server to 127.0.0.1. This is not a public unauthenticated API decision:
production authentication, authorization, rate limits, licensing, and deployment
still require review. No startup migration or automatic seed occurs.

## Validation and scope

Network-blocked tests cover validation, response contracts, unavailable readers,
and errors. Disposable PostgreSQL tests cover filtering, pagination, committed vs
rolled-back visibility, and detail consistency. Generate OpenAPI/client artifacts
from routes and verify additive compatibility. Keep the existing Floci delivery-DLQ
gap explicit; these synchronous reads do not depend on that unsupported behavior.
The full raw-to-API composition test remains a separate Phase 2 acceptance increment.
