# ADR-013 — Immutable provider mapping revisions

**Status:** Accepted for the internal Phase 2 domain slice; persistence and review workflow deferred
**Date:** 2026-09-22

## Context

The canonical model requires provider mappings to be versioned/auditable, while
the ingestion design requires ambiguous matches to be reviewed. The conceptual
field list does not specify revision identity, supersession, or historical lookup.
Overwriting a mapping would make retained research impossible to reproduce.

## Decision

- A `ProviderEntityKey` contains `data_source_id`, `provider_entity_type`, and
  `provider_entity_id`. Provider type/ID strings are opaque, case-sensitive,
  nonblank, unpadded values. Adapters own namespaces (including competition/season
  qualifiers when provider IDs are not globally unique). Never key by venue alone.
- `ProviderMappingRevision` identity is `(key, revision)`, with integer revisions
  starting at 1. These internal records extend the conceptual mapping fields;
  they are not a published API/event contract or a new canonical business ID.
- Each immutable revision carries a typed `canonical_entity_id`, `mapping_method`,
  optional `confidence`, `validated_by`, `validated_at`, `available_at`,
  `ingested_at`, and `status` (`MAPPED` or `REVOKED`). Initial target types are
  Sport, Competition, Season, Participant, Event, and Venue IDs already implemented.
  A source is not a venue target. No market IDs are scaffolded yet.
- Confidence is either unknown (`None`) or a finite Decimal in [0, 1], expressing
  method-specific match quality, not a calibrated probability. It never selects
  a winner, approves a candidate, or grants execution permission.
- These are recorded validation decisions, not candidate proposals. The caller
  supplies validation method and actor provenance. The value object cannot prove
  the actor's identity or review authority. Ambiguous proposals must stay outside
  the resolver; no fuzzy matching or automatic confidence threshold is introduced.
- All three timestamps must be aware. Compare UTC instants, including DST folds.
  For this *mapping decision*, require `validated_at <= available_at <= ingested_at`.
  Availability is when that decision could first be used; it cannot be backdated
  to the event date. Later ingestion of an earlier documented decision is allowed.
  This ordering is not a blanket rule for all provider facts.
- A complete history for one key has contiguous revisions, no duplicate revision
  numbers, a stable target ID type, and nondecreasing availability and ingestion
  timestamps. Equal timestamps are allowed; revision number breaks ties.
  The first revision must be MAPPED. A revocation retains its preceding target
  for audit. A later MAPPED revision can correct or restore the target.
- Lookup validates the supplied complete history, then selects the highest
  revision with `available_at <= as_of`. It returns that MAPPED revision, or None
  if not yet available / revoked / absent. It never falls back through revocation
  to an earlier mapping. Invalid histories fail closed, including malformed future
  revisions. Input order does not affect selection and input records are not changed.

## Boundaries and consequences

The initial implementation is pure, network-free, and in-memory. It cannot detect
an omitted tail of history; callers must supply a complete per-key history from a
pinned dataset snapshot. Persist the selected key/revision with normalized output
and dataset/normalizer versions; a mapping cutoff alone is not a full no-lookahead
guarantee for quotes, features, or results.

Persistence must later enforce append-only storage, transactional revision
allocation, canonical-reference existence/type, and exact-replay idempotency.
The in-memory validator rejects even identical duplicate revision rows; transport
redelivery handling belongs at the storage/ingestion boundary. Many source keys
may reference the same canonical entity. No one-to-one provider rule is imposed.

Reviewer authentication/authorization, candidate/review UI, evidence storage,
provider namespace catalogs, SQL migrations, and external contracts are deferred.
Introducing those protected capabilities requires their own review. This ADR
does not authorize any execution, production access, or provider licensing change.

## Alternatives

- Mutable latest-only mapping: rejected because it loses correction history.
- Highest confidence wins: rejected because ambiguity must not resolve silently.
- Full bitemporal storage now: deferred; dataset snapshots plus explicit decision
  availability address this internal slice without prematurely choosing SQL design.

## Related

- [Canonical model](../architecture/canonical-domain-model.md)
- [Ingestion and time semantics](../architecture/data-ingestion-normalization.md)
