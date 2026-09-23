# Replay Dataset Snapshot Manifest — v1

**Status:** Internal contract defined; implementation pending  
**Decision:** [ADR-026](../adr/ADR-026-replay-dataset-manifest.md)

## Purpose and scope

Identify a fixed, bounded collection of retained synthetic mapped-event inputs
that can be reproduced without current-state reads. This is the first narrow
dataset snapshot contract, not a historical research dataset or backtest API.
The existing mapped replay helper verifies one capture; a manifest verifier is
not yet implemented. No new root command or generated artifact exists.

## Wire shape

All object fields below are required; unlisted fields are rejected. Literal
values are exact and case-sensitive. Capture and receipt-pin arrays are sets for
identity purposes with the canonical order defined below; arrays inside receipts
retain their existing codec semantics, including role-ordered mapping revisions.
Identifiers retain their existing opaque,
case-sensitive semantics. This table defines a contract, not example JSON with
placeholder hashes that might be mistaken for a valid fixture.

| Object | Field | Value |
| --- | --- | --- |
| Envelope | `dataset_version` | Lowercase 64-character SHA-256 hex digest of canonical `manifest` bytes |
| Envelope | `manifest` | Manifest object |
| Manifest | `format` | Integer `1`, not Boolean |
| Manifest | `kind` | `MAPPED_EVENT_REPLAY` |
| Manifest | `usage` | `REPLAY_ONLY` |
| Manifest | `captures` | Nonempty array of Capture objects |
| Capture | `raw` | Full existing `RawPayloadReference` representation |
| Capture | `receipts` | Array of ReceiptPin objects; empty only for a verified empty raw event array |
| ReceiptPin | `acceptance_key` | Existing lowercase SHA-256 lineage digest |
| ReceiptPin | `receipt_sha256` | SHA-256 of the canonical format-2 receipt bytes |
| ReceiptPin | `receipt` | Full existing `{format: 2, candidate: ...}` receipt object |

`raw` uses the same representation as `candidate.raw` in format-2 receipts:
`capture`, `sha256`, and `size_bytes`. The capture contains the typed
`data_source_id` value object, `resource`, `ingested_at`, `effective_at`,
`observed_at`, and `available_at`. Optional timestamps are explicit nulls, never
omitted or filled from another clock. See [raw storage](../adr/ADR-015-raw-payload-storage.md).

Each embedded receipt pins the full event/participant output, source-scoped
provider event key, raw reference, parser/normalizer/context versions, selected
mapping revisions, cutoff, canonical references, and label guards. The format-2
codec remains authoritative; this contract does not redefine its nested fields.
See [receipt compatibility](../adr/ADR-025-mapping-backed-fixture-context.md).

No `created_at`, mutable dataset alias, storage locator, or current database query
contributes to this manifest. Future catalog/audit metadata may record creation
separately. Identical retained inputs must yield the same version regardless of
when or where they are assembled. Dataset version is a content identity, not an
incrementing counter, event ID, receipt format, or normalizer version.

## Canonical bytes and identity

1. Validate all values and the receipt codec/version support before encoding.
2. Normalize aware timestamps to UTC using the existing receipt convention;
   preserve nulls. Use the existing exact Decimal-string and typed-ID encodings.
   Sort participant entries as required by the receipt codec. Never round evidence.
3. Sort captures lexicographically by canonical ASCII JSON bytes of their complete
   `raw` reference. Sort receipt pins within a capture by canonical ASCII JSON
   bytes of the receipt's `candidate.provider_key`.
4. Encode JSON with sorted object keys, compact separators (`,` and `:`), ASCII
   escaping, no trailing newline, and UTF-8 bytes. This matches the existing
   Python JSON encoding convention, not a claim of RFC 8785 compatibility.
5. Compute each receipt hash over the canonical encoded `receipt` object. Compute
   `dataset_version` over the canonical encoded `manifest` object only, excluding
   the outer envelope and therefore the version itself.
6. Encode the envelope by the same rules. The canonical envelope is limited to
   1 MiB (1,048,576 bytes); larger collections require a later partitioned format,
   not silent truncation. Raw bodies are not embedded.

The in-memory builder may accept unordered valid inputs and canonicalize them.
A wire reader must enforce the size limit before parsing, reject duplicate JSON
keys/nonstandard numeric constants/unknown fields/unsupported versions, and require
its input bytes to equal canonical re-encoding. This rejects alternate ordering,
whitespace, timestamp encodings, and duplicate members instead of silently repairing
stored content. Hash mismatch is a failure, not a request to regenerate a new pin.

Changing capture metadata, raw bytes, output, context, selected mappings, versions,
or membership changes the dataset version. Input order and equivalent timestamp
offsets supplied to the builder do not. Never rewrite an old manifest when
normalization changes; build a different snapshot, preserving the old inputs.
An implementation must not silently relabel an old receipt with new versions.

## Structural invariants

- Each capture's full raw reference is unique. Identical bodies acquired under
  different capture metadata are distinct captures, not checksum duplicates.
- Every receipt decodes through the existing strict format-2 codec and has mapping
  evidence. Recompute its acceptance key and receipt hash; both must match pins.
  Full receipt hashes are necessary because acceptance keys exclude event/entries.
- The only supported pair is parser `synthetic-odds-events-v1` and normalizer
  `synthetic-event-mappings-v1`. Unknown versions fail closed, without raw I/O.
- Every receipt's raw reference equals its enclosing capture reference. Provider
  and mapping keys retain source scope; `DataSource` never becomes `Venue`.
- Provider event keys and canonical event IDs must be unique within each capture.
  An acceptance key may occur only once in a manifest. Duplicate entries, even
  identical ones, are errors rather than an instruction to deduplicate.
- Different captures may contain the same canonical event ID or provider event
  key, because capture identity distinguishes observations. This format imposes
  no cross-capture temporal precedence or merge rule. Do not flatten it into a
  latest-event table or a historical timeline.
- Structural validation cannot prove raw existence, complete event coverage,
  actual database acceptance, retention rights, or historical availability.
  A full receipt is not an authenticated acceptance attestation.

## Verification and replay

After structural validation, a verifier reads each exact raw reference using a
caller-supplied `RawPayloadStore`. Existing integrity checks verify size, body hash,
and capture metadata. It passes the complete group of decoded candidates to
`replay_mapped_fixture_events`, which checks exact event coverage, source/label
guards, and full candidate equality using retained context.

An empty receipt group is valid only when the verified raw payload parses as an
empty event array. Never discard a raw event to make a receipt subset pass.
Manifest/capture ordering is canonical; each capture's replay output follows raw
event order. A verifier returns success only after all captures pass; an error in
the final capture cannot return a successful prefix. No partial writes occur
because this operation is read-only.

Missing bytes, integrity failures, unsupported versions, incomplete coverage, or
reconstruction drift fail the snapshot. Do not fetch provider data, manufacture
replacement timestamps, read current mappings/references, mutate receipts, insert
events, or publish notifications as recovery. Storage transport errors propagate.
Later mapping revocation does not alter retained evidence, but continues to block
fresh normalization at the relevant cutoff under the normal resolver rules.

Exporting trusted receipts from PostgreSQL is a separate composition step. It must
use immutable accepted receipts rather than the current-state event API and retain
all receipts required for each included capture. A caller-supplied candidate alone
does not prove persistence. No receipt discovery query or database export command
is introduced by this specification.

## Availability constraints and historical exclusion

| Retained input | What it establishes | What it does not establish |
| --- | --- | --- |
| Raw `effective_at` | Underlying fact time when known | Strategy availability |
| Raw `observed_at` | Provider observation time when known | Strategy availability |
| Raw `available_at` | Recorded capture availability when known | Availability of every normalized fact or context dependency |
| Raw `ingested_at` | System capture time | Historical availability by inference |
| Selected mapping revisions | Their recorded decision availability and resolution cutoff | Availability of canonical names/attributes or authored fixture fields |
| Retained canonical/authored context | Exact values used for replay | When a historical strategy could have known those values |

`usage=REPLAY_ONLY` is a mandatory restriction, not a configurable assertion of
quality. A consumer asking for historical decision inputs must reject every v1
manifest, even if raw and mapping availability are both known and before its
decision time. Unknown context availability cannot be supplied by `as_of`, event
start, manifest assembly time, receipt acceptance, confidence, or a digest.
Do not derive a batch-level minimum/maximum timestamp and call it eligibility.

Future research manifests must separately pin normalized historical rows and their
availability evidence, features/models when present, and outcome/settlement labels.
Decision inputs must satisfy `available_at <= simulated_decision_time`, with all
consumed dependency evidence accounted for; pregame decisions must precede event
start. Later outcome labels may support evaluation, never leak into decision-time
features. A future contract must define these roles and checks before research use;
none are implemented or authorized by replay success.

## Required implementation evidence

- Golden canonical bytes/dataset versions and full receipt hashes; legacy
  format-1/2 bytes and acceptance keys remain unchanged.
- Builder order/offset equivalence; changing any retained input or projected
  event output changes identity, even when the acceptance key is unchanged.
- Rejection of duplicate keys/members, malformed types/digests, unknown fields
  and versions, noncanonical bytes, unsupported legacy receipts, and oversize
  input before storage access.
- Complete multi-capture replay, verified empty captures, missing/corrupt raw
  bytes, wrong capture metadata, incomplete coverage, and final-capture failure.
- Persisted format-2 receipts replay against Floci after current mappings and
  reference values change; no provider/current-state reads or writes are needed.
- Unknown raw availability remains null. Known raw and mapping availability
  still cannot make a v1 manifest historically eligible.

Run normal credential-free root validation for each implementation handoff.
Unit tests use no network; storage integration uses disposable Floci resources.
No provider calls, paid data, new production resources, or licensing changes are
required. Manifest value objects, codecs, golden vectors, storage, and verifiers
remain pending; this document is not evidence that those tests already pass.
