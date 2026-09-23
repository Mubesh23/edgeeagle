# ADR-032 — Private local retained-dataset API

**Status:** Accepted; local API and generated-client contract implemented
**Date:** 2026-09-23

## Decision

Expose ADR-031 through two additive read-only operations:

- `GET /v1/datasets`: all selected root metadata as `{items: [...]}`, sorted by
  root hash, bounded by the existing 32-entry catalog. No pagination or bucket scan.
- `GET /v1/datasets/{rootHash}/inspection`: fresh complete replay of one selected
  lowercase SHA-256 root. No stored verification flag or background job.

Responses preserve the typed ingestion catalog results, including nested raw
provenance, unknown timestamps, version pins, literal replay states and mandatory
replay-only exclusions. This is a retained-artifact inspection, not evidence of
historical eligibility, kickoff accuracy, provider rights or database acceptance.
HTTP serialization and generated clients do not reimplement replay logic.

The default application returns sanitized 503 responses without configuring any
catalog or storage. A separate explicit local factory loads the ignored ADR-031
configuration once; restart to change selected roots. It uses existing loopback
Floci composition, dummy credentials, bounded SDK timeouts and request-scoped
clients closed on success and failure. It needs no PostgreSQL connection.

Bind the API and any development proxy only to 127.0.0.1, consistent with
ADR-024's local-only boundary. The existing Vite development proxy may forward
same-origin `/api/*` requests to the loopback API. Reverse proxies are not
categorically prohibited; external exposure is. Do not expose either server to
the LAN or internet, use externally reachable proxies or tunnels, or host/deploy
this private interface. Loopback binding is an operator-only development boundary,
not authentication or authorization.
No CORS, auth policy, network/IAM resource, hosting, UI or MCP tool is added.
Production exposure and multi-user access still require human security/licensing
review. Do not run against private captures in hosted CI.

This clarification was explicitly approved by the owner: permit the existing
loopback-only development proxy, while preserving the prohibition on external
exposure. It changes no runtime networking configuration, CORS policy, provider
rights or replay-only eligibility.

Malformed hashes return 422 before storage access; unselected hashes return 404
before storage access. Missing/corrupt retained artifacts and storage transport
failures return sanitized 503, never partial results or automatic repair.
Unexpected programming failures remain 500. Catalog responses, including handled errors,
carry `Cache-Control: no-store` so a fresh inspection is never represented as a
cacheable durable verification. No raw bytes, bucket names or configuration paths
are returned. Resource/provider identifiers already present in provenance remain
private response data.

## Validation and boundaries

Test default isolation, bounded listing, hash validation, selection, fresh replay,
error sanitization, client cleanup and unchanged eligibility. Local integration
uses authored captures in disposable Floci buckets, verifies unchanged objects,
and rejects a missing page without repairing it. Generate OpenAPI/TypeScript
artifacts and check additive compatibility. No migration, provider fetch or
change to ADR-029 replay is needed. Synchronous bounded inspection is sufficient
for this single-operator slice; public rate limits and large asynchronous research
jobs are not implied by it.
