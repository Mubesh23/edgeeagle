# ADR-027 — Immutable replay manifest storage

**Status:** Accepted for the internal storage contract; implementation pending  
**Date:** 2026-09-23

## Context

[ADR-026](ADR-026-replay-dataset-manifest.md) defines bounded canonical manifest
bytes, content-derived dataset versions, and read-only artifact verification.
Callers currently retain those bytes themselves. No port retrieves a manifest by
dataset version. Reconstructing it from current tables would defeat the retained
snapshot boundary; a mutable filename or a latest-version alias would not pin it.

The TDD places retained analytical artifacts in S3. This decision follows the
conditional-write pattern in [ADR-015](ADR-015-raw-payload-storage.md), but does not
represent an internal manifest as a provider raw capture. Those records have
different identities, provenance, and purposes.

## Ownership and interface

Ingestion owns a `ReplayManifestStore` port and `ManifestIntegrityError` exception.
The initial interface is:

```python
put(body: bytes) -> str
get(dataset_version: str) -> bytes | None
```

`put` accepts canonical ADR-026 envelope bytes and returns their validated
`dataset_version`. `get` accepts that exact version and returns the exact canonical
envelope bytes, or None for an absent object. A version must be a lowercase
64-character SHA-256 hex string; reject other types/values before storage I/O.
It is not a URL, user-chosen path, label, S3 VersionId, ETag, or envelope checksum.
The dataset version remains the hash of the inner canonical `manifest` object,
not a newly invented hash of the entire envelope.

Persistence implements the port as `S3ReplayManifestStore` using a caller-supplied
S3 client, bucket, and the existing inward-owned `EventReceiptCodec`. Ingestion
does not import persistence. The adapter uses `decode_manifest` for structural
validation rather than duplicating the manifest or receipt codecs. It accepts
only the currently supported ADR-026 format/kind/usage and receipt versions.

The port exposes no overwrite, delete, listing, mutable alias, catalog search,
database discovery, or publish operation. No storage locator enters the manifest.
Caller configuration resolves the manifest bucket separately from the raw store;
the two may share a bucket or use different buckets without changing identity.

## Object layout and bounded reads

Storage layout v1 is fixed:

```text
snapshots/replay-manifests/v1/<dataset_version>.json
```

The object body is the unmodified canonical envelope, with `application/json`
content type on writes. No custom S3 metadata is required for identity or validity;
all authoritative metadata is inside the envelope. Content type and ETag must not
substitute for decoding, full receipt pin validation, and requested-version checks.
Changing incidental S3 metadata does not change dataset identity.

Retain the inclusive ADR-026 1 MiB limit. On reads, close the response body on every
path, including rejection. Require a nonnegative integer ContentLength no larger
than the limit; reject an invalid/oversize response without allocating that body.
Read at most limit + 1 bytes, check the actual length against ContentLength and
the limit, and decode the exact bytes. Never return a truncated prefix, use an
unbounded read, or silently re-encode a noncanonical stored object.

After strict decoding, the validated envelope's dataset version must equal the
requested version. A perfectly valid manifest stored under another version's key
is corruption at this boundary, not an alternative result. Do not trust the key
or S3 metadata alone. No raw capture is read while retrieving manifest metadata.

## Write and retry behavior

1. Type/size/strict-codec validation completes before S3 I/O. Invalid caller bytes
   raise TypeError/ValueError as appropriate, without a storage write or repair.
2. Derive the fixed key from the validated embedded dataset version. Send one
   conditional `PutObject` with `IfNoneMatch="*"`; never use a HEAD-then-write
   sequence or an unconditional overwrite.
3. An acknowledged first write returns the dataset version. No read-after-write
   claim of permanent retention is made.
4. For `PreconditionFailed`, use the same integrity-checked `get` path and require
   byte-for-byte equality with the proposed envelope before returning success.
   This handles exact retries and concurrent identical writers without accepting
   a different body under the same version, even in a digest-collision scenario.
5. A missing object after that precondition failure, malformed stored content,
   requested-version mismatch, or unequal existing bytes raises
   `ManifestIntegrityError`. Never delete/replace a corrupt object automatically.

Only `NoSuchKey` from `get` means absence. `NoSuchBucket`, access denial,
conditional-race errors other than `PreconditionFailed`, throttling, transport
failures, and stream failures propagate as errors, not None or success.
Stored-content/length/codec failures become `ManifestIntegrityError` with their
cause retained. There is no adapter retry loop. The caller owns SDK configuration,
timeouts, retry policy, and ambiguous-write recovery by retrying identical bytes.

## Storage is not artifact verification

A stored manifest is structurally valid replay metadata, not a certificate of
successful replay, database acceptance, historical eligibility, or retention rights.
`put` does not call `verify_manifest`, read raw data/current mappings, or publish an
event. Even a structurally valid incomplete capture can be stored, then fail the
separate whole-snapshot verifier. Do not add a durable `verified=true` flag that
can outlive the raw artifacts it purportedly describes.

A caller retrieves bytes by its trusted dataset version, handles None as missing,
then explicitly calls `verify_manifest(body, codec, raw_store)` when replay evidence
is required. A missing manifest must not be reconstructed from current state; a
missing raw object must not trigger a provider fetch. S3 operations, raw verification,
and any future PostgreSQL catalog transaction remain separate. Orphan artifacts are
possible; this contract does not introduce garbage collection or reference counting.

Hashes and conditional writes provide application integrity/immutability, not
authenticated ownership or protection from an authorized external writer deleting
objects. There is no Object Lock, new IAM policy, encryption/retention configuration,
production bucket, lifecycle change, or deployment in this decision. A future
production retention/catalog design still needs its own review. `REPLAY_ONLY`
remains mandatory regardless of whether storage and verification both succeed.

## Compatibility and alternatives

- Preserve ADR-026 manifest/golden bytes, dataset versions, receipt formats and
  acceptance keys, and ADR-015 raw keys/metadata. No migration rewrites artifacts.
- No generated API/event contract, new runtime dependency, root command, or
  provider licensing assumption is introduced.
- Do not reuse `RawPayloadStore`: it would fabricate provider capture provenance
  and would require raw capture metadata rather than dataset-version lookup.
- Do not add a PostgreSQL catalog yet: exact lookup needs no listing/indexing
  capability, and a catalog would require separate publication/consistency rules.
- Do not store only event IDs: the manifest already pins full retained evidence.

## Incremental implementation and validation gates

1. This contract and documentation links; no executable storage support claimed.
2. Ingestion-owned port/error plus the S3 adapter and network-disabled unit tests.
   Cover invalid input before I/O, fixed keys, exact bytes, conditional writes,
   stream closure, bounded/short reads, strict decoding, wrong-version objects,
   exact/conflicting retries, and propagated service failures.
3. Disposable Floci tests for first write, exact/concurrent retries, absence,
   direct conditional-write enforcement, and out-of-band corruption. Prove that
   storing another valid envelope under the requested key is rejected and that
   replay does not overwrite it. Corrupt only test-owned objects.
4. Compose retrieve-by-version with existing replay using retained PostgreSQL
   receipts and Floci raw storage. Prove lost raw data fails replay while the
   unchanged manifest remains retrievable. No current-state reconstruction or
   publication is permitted.

Implementation and its intrinsic tests may form one coherent increment; keep
independently reviewable composition work separate when practical. Run the cheapest
relevant checks during development and `scripts/validate` before handoff. Normal
tests use fixtures, disposable local resources, and no paid provider/AWS credentials.
The known Floci delivery-DLQ gap remains unrelated and unresolved.
