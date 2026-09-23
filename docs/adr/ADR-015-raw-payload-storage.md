# ADR-015 — Content-addressed raw payload storage

**Status:** Accepted for internal Phase 2 storage  
**Date:** 2026-09-22

## Context

The ingestion design requires exact raw responses retained before transformation.
It leaves identity, capture metadata, and replay behavior unspecified. This
decision implements the S3 direction in the TDD without changing ADR-002's broader
proposed status or introducing production infrastructure.

## Decision

The pure domain owns a `RawPayload` record and `RawPayloadStore` protocol.
The existing persistence package implements S3 storage with a caller-supplied
client and bucket; no SDK discovery, bucket creation, or API wiring occurs there.

Raw payloads contain exact bytes, source identity, a logical resource label (not
a credential-bearing URL), and caller-supplied ingestion time. Optional effective,
observed, and available times preserve knowledge without inventing unknown values.
All times are aware and serialized as UTC instants. Availability, when known,
must not exceed ingestion. No other timestamp ordering is inferred.

Storage format v1 uses the exact bytes as the object body and a canonical ASCII
JSON capture descriptor in S3 user metadata. The descriptor is capped at 1,500
bytes to stay below S3's user-metadata limit with the remaining fixed fields.
SHA-256 hashes independently identify payload bytes and descriptor. Keys partition
by escaped source, resource, UTC ingestion date, then both hashes. Keys exceeding
S3's 1,024-byte limit are rejected before I/O. Empty and non-JSON payloads are valid.
Different captures of identical bytes remain distinct when metadata differs.

Writes use `If-None-Match: *`, never a check-then-unconditional-write sequence.
An existing object is accepted only after checking exact body and metadata.
Conflicting/corrupt data raises an integrity error. Writes return a reference
containing capture metadata, SHA-256, and byte length. Reads require that reference
and verify it before returning bytes, without needing the original body.
Only `NoSuchKey` becomes absence; authorization, transport, conditional-race,
and other service errors propagate. A caller may retry the same unchanged record.
The adapter exposes no overwrite or delete operation.

This is application immutability, not protection against another authorized
writer deleting/replacing objects. Object Lock, IAM, retention policies, catalog
indexing, streaming/multipart large datasets, and deployment require later work.
This initial in-memory interface is for bounded responses, not bulk archives.

## Consequences

- Retries must retain the original timestamps; no clock is read by the adapter.
- No atomic transaction spans PostgreSQL and S3. Future ingestion must persist
  raw data first and tolerate orphan objects/replay after downstream failures.
- Provider/canonical entity IDs remain in raw bytes and later normalization
  lineage; a response can contain many entities. No fabricated model, feature,
  dataset, or normalization version is attached before those stages exist.
- Callers must establish retention rights before writing. This interface grants
  no licensing permission and stores no request headers or credentials.
- Unit tests remain network-disabled; Floci integration uses disposable buckets,
  dummy credentials, and explicit loopback endpoints. Emulator gaps fail visibly.

## Related

- [Ingestion design](../architecture/data-ingestion-normalization.md)
- [Testing strategy](../development/local-development-testing.md)
