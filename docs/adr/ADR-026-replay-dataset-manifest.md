# ADR-026 — Versioned replay dataset manifests

**Status:** Accepted; codec and read-only verification implemented; storage follows ADR-027  
**Date:** 2026-09-23

## Context

The PRD requires dataset versions and leakage-safe research. The TDD separates
current PostgreSQL state from retained analytical inputs. ADR-025 now reproduces
one complete raw capture from retained mapped receipts, without current reference
reads. There is no contract identifying a fixed collection of those inputs.

Reproducibility is not historical eligibility. Raw availability may be unknown;
selected mapping revisions have decision timestamps, but the retained canonical
records and authored fixture context have no independent availability evidence.
An event's start time, a mapping cutoff, or a later snapshot creation time cannot
fill that gap. A manifest must not turn successful fixture replay into a claim
that a historical strategy could have known the inputs.

## Decision

Define the bounded, internal
[replay dataset manifest v1](../architecture/dataset-snapshot-manifest.md).
Its only supported kind is `MAPPED_EVENT_REPLAY`, with usage `REPLAY_ONLY`.
It pins a nonempty collection of complete raw captures and embeds their full
format-2 receipts. The complete canonical manifest content determines its
SHA-256 dataset version. It is not an API, domain event, normalized Parquet schema,
or the eventual general-purpose research dataset format.

Embed receipts rather than referencing mutable tables or relying on event IDs
alone. Pin their full canonical bytes as well as their existing acceptance keys:
the acceptance key deliberately excludes event/entry output. Keep original
source/provider/canonical identities, capture timestamps, selected mapping
revisions, reference values, and parser/normalizer/context versions unchanged.
Do not add fabricated model, feature, prediction, or strategy versions.

Raw bodies remain in the existing raw store; the manifest carries full
`RawPayloadReference` values, not bucket names, credentials, mutable URLs, or
local absolute paths. Resolution uses caller-supplied storage configuration.
Missing artifacts fail closed; a replay cannot repair itself by fetching providers
or consulting current canonical/mapping tables.

The manifest's structural validation, artifact verification/replay, and historical
eligibility are separate outcomes. Every v1 manifest is ineligible as a historical
decision-input dataset, even if every known timestamp precedes a supplied decision
time. Unknown availability stays unknown. A future research contract must define
availability evidence for every consumed fact and context dependency, per-record
decision-time filtering, and outcome/label separation before relaxing this limit.

## Boundaries and compatibility

The ingestion application will own manifest values, deterministic identity, and
replay orchestration, depending only inward on domain. Persistence owns receipt
codec/storage adapters. An inward-owned receipt codec port can bridge existing
format-2 serialization without importing persistence into ingestion or duplicating
the receipt codec. Moving codec ownership, if chosen instead, needs an explicit
follow-up decision and byte/digest compatibility tests.

Preserve format-1/2 receipt bytes, acceptance keys, existing migrations, and event
envelopes. Manifest format 1 is independent of receipt format 2. No migration,
new dependency, external contract, deployable, storage bucket, retention policy,
IAM change, or provider licensing assumption is introduced by this ADR.

This accepts a narrow metadata contract under the TDD's storage direction; it
does not change ADR-002's broader proposed status or select a production catalog.
Digests detect drift relative to trusted pins, not malicious replacement of both
content and pins. Export/retention rights remain a caller responsibility.

## Alternatives

- Current-state queries plus a timestamp: cannot reproduce reference edits.
- Event IDs or acceptance keys alone: do not pin full output or retained context.
- Raw checksums alone: omit capture metadata and normalization context.
- A single `available_at` for the entire collection: loses per-input semantics
  and conceals unknown context availability.
- A universal Parquet/model/backtest manifest now: premature; those artifact
  contracts and historical evidence rules are not implemented yet.

## Incremental delivery

1. This ADR and the normative specification, with implementation status explicit.
2. Pure manifest values, strict codec, canonical identity, limits, and offline
   test vectors. Preserve receipt compatibility through a codec adapter/port.
3. Read-only complete-snapshot verification through existing raw storage and mapped
   replay, with missing/corrupt inputs and later mapping edits covered locally.
4. Separately design immutable manifest persistence/cataloging and historical
   availability evidence. Do not claim either from an in-memory value object.

Each increment is independently validated and committed. The specification lists
the acceptance cases for subsequent implementation.

## Implementation status

Ingestion's `manifests` module now implements frozen `ManifestCapture` and
`ReplayDatasetManifest` values plus `encode_manifest`/`decode_manifest`. Its
`EventReceiptCodec` protocol is implemented by the pure persistence adapter
`receipts.EventReceiptCodec`, delegating to the unchanged receipt codec. No codec
ownership was moved. Encoding checks receipt decoding and derives the pins;
decoding reconstructs validated values and requires exact canonical re-encoding,
recomputing all pins rather than accepting or repairing supplied hashes.

Offline tests pin independently assembled golden bytes/hashes, ordering/offset
equivalence, output drift, immutable values, duplicate identities, malformed and
noncanonical inputs, and the inclusive 1 MiB limit. The size check precedes JSON
parsing on reads. Existing format-1/2 compatibility tests remain unchanged.
The codec alone performs structural metadata validation: empty receipt groups are
not verified empty captures.

`snapshot_replay.verify_manifest(body, codec, store)` now validates the entire wire
manifest before raw I/O and composes the existing mapped replay adapter for every
capture. It returns a fully materialized tuple of candidate groups in canonical
capture order, preserving raw event order within groups and empty groups. Any
failure raises before returning a result; there is no successful-prefix iterator,
retry, write, current-state lookup, or publication. Store/replay exceptions propagate.
The caller supplies the store and its transport/timeouts; no database transaction
spans verification. Success verifies these reads, not future artifact retention.

Network-disabled tests cover multi-capture ordering, empty groups, final-capture
failure, unsupported metadata before I/O, missing/corrupt bytes, transport errors,
incomplete coverage, and projection/label drift. Disposable PostgreSQL/Floci tests
use two accepted receipts plus an empty capture after mapping revocation/reference
edits, and reject later deletion or body/metadata corruption of the final object.
Accepted records remain unchanged and no outbox entries appear. Manifest storage,
receipt discovery/export, acceptance authentication, historical eligibility, and
new root commands remain outside this increment.
