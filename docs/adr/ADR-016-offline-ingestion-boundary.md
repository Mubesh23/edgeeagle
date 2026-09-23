# ADR-016 — Offline raw ingestion boundary

**Status:** Accepted for Phase 2 fixture ingestion  
**Date:** 2026-09-22

## Decision

Add `libs/python/ingestion` as a library, not a worker or deployable. Its application
boundary depends only on domain records and ports. It owns an
`OfflineDatasetImporter` protocol with `read() -> RawPayload` and an
`ingest_raw(importer, store)` operation returning a verified storage receipt.
An adapter submodule implements local-file acquisition. Neither the domain nor
application orchestration imports concrete storage adapters.

Start with this one acquisition capability from the ingestion design. Sports,
sportsbook, prediction-market, and execution interfaces will be separate contracts
when their actual consumers exist; a universal provider interface is not added.

The local-file adapter takes an explicit trusted path, capture metadata, and a
positive byte limit. It reads at most limit + 1 bytes and rejects oversized input.
It neither parses payloads nor reads a clock, environment, network, or sidecar.
Missing/unreadable files fail visibly. Empty or malformed payloads can still be
retained for later validation. The path is deployment/test configuration, not
untrusted user input; this adapter is not a file-access authorization boundary.

Orchestration reads once, validates the returned record type, and calls the raw
store once. It returns only after the store acknowledges the expected checksum,
size, and capture identity. Acquisition/storage failures propagate; there are no
hidden retries, canonical writes, or callbacks before retention succeeds.

## Replay and provenance

Reuse the same bytes and original capture timestamps on retry, as specified by
[ADR-015](ADR-015-raw-payload-storage.md). Changing a local file changes its content
identity; this importer is not a snapshot manager or acquisition deduplication
ledger. Callers must pin input files or replay retained references for research.

The existing synthetic odds fixture is exercised with an explicitly synthetic
source identity and resource label. Its sample provider timestamps and creation
date are not inferred as availability/observation times. The fixture sidecar
continues to document its authored provenance; this is not a live Odds API adapter
or Football-Data importer. Unknown capture timestamps stay unknown.

Retention rights and safe inputs remain caller prerequisites. No licensing,
authentication, API, event, IAM, or production infrastructure policy changes.
Streaming archives, HTTP acquisition, quotas/retries, parsing, quarantine,
normalization, lineage catalogs, and durable orchestration remain deferred.

## Validation

Network-disabled unit tests prove byte fidelity, limits, failure propagation,
and receipt integrity. Floci integration composes the local fixture adapter with
the S3 adapter using disposable buckets and verifies exact retention and replay.
This is fixture -> raw only, not the Phase 2 raw -> canonical -> event -> API exit.
