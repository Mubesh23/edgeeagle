# ADR-017 — Versioned synthetic event normalization

**Status:** Accepted for Phase 2 fixture validation  
**Date:** 2026-09-22

## Context

The authored odds fixture contains event IDs, competition keys, start times, and
home/away labels. It has no participant IDs, season ID, or event status. Treating
names as stable provider IDs or inferring lifecycle state would hide ambiguity.

## Decision

Add a fixture-only adapter to the ingestion library. It reads an existing raw
reference through `RawPayloadStore`, independently checks returned bytes against
that reference, then parses the entire bounded JSON batch. It never reacquires a
provider response or writes canonical records. Invalid batches fail as a whole;
the retained raw object remains available for investigation. Durable quarantine
is not implemented by a raised validation error.

Parser v1 requires a UTF-8 JSON array of event objects with nonblank, unpadded
string IDs, competition keys, home/away labels, and aware ISO start timestamps.
Reject duplicate JSON keys, nonstandard numeric constants, duplicate event IDs,
and identical home/away labels. Unknown fields are tolerated and remain in raw
storage. Bookmakers/markets/prices are not interpreted or certified as valid.
Provider-native staging stays private to this adapter.

Normalization v1 requires exactly one explicit frozen binding per event. Each
binding supplies a source-scoped event key, exact competition/home/away labels,
canonical event ID, sport/competition/season records, two canonical participants,
status, and a nonblank context version. Matching is case-sensitive, with no
trimming/fuzzy matching, label-derived IDs, season inference, or status default.
Bindings must not collapse multiple provider events onto one canonical event.
The existing sport-neutral context validator checks the resulting relationships.
HOME/AWAY cardinality belongs to this fixture adapter, not the canonical model.

Return immutable canonical event candidates with event/entries, raw reference,
source-scoped provider event key, parser/normalizer versions, and context version.
The caller must retain the immutable context identified by that version to
reproduce resolution. Candidates are not persisted events or historical datasets.
No fixture timestamps become observed/available times; those remain exactly as
recorded in the raw capture. No model, feature, or dataset versions are fabricated.

## Scope and consequences

Explicit fixture bindings are test configuration, not new production mapping
decisions or authenticated reviews. They do not replace ADR-013/014 mapping
history. A real provider normalizer must resolve provider identities against
pinned mappings and preserve decision revisions before production use.

This adds fixture -> retained raw -> canonical candidate validation, not the
Phase 2 database/event/API exit. Live provider compatibility, market normalization,
review workflow, durable lineage/context catalogs, and transactional publication
remain deferred. No provider calls, licensing assumptions, API/schema migrations,
or infrastructure changes are introduced.

## Validation

Network-disabled tests cover parsing, mismatches, ambiguity, integrity, and
determinism. Floci integration proves the candidate comes from retained bytes and
that original synthetic provenance remains unchanged.
