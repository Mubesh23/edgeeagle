# ADR-040 — Binary-market mapping boundary and local order-book inspection API

**Status:** Accepted
**Date:** 2026-10-09

## Context

[ADR-039](ADR-039-kalshi-orderbook-fixture-adapter.md) establishes an offline
Kalshi binary-order-book parser and explicitly leaves canonical mapping and API
exposure for later decisions. The product taxonomy includes prediction-market
contracts that can be expressed from an underlying outcome distribution, but the
implemented canonical market currently supports only soccer regulation-time 1X2.
An order book can be inspected as venue-native evidence without claiming that its
contract has already been understood or mapped to that canonical market.

## Decision

### Canonical mapping boundary

- Map a binary contract to canonical outcome semantics only when its YES condition
  is logically equivalent to a known set of outcomes from a supported canonical
  distribution and its event, period, participant, and settlement conditions
  match exactly.
- NO is the complement of the explicitly mapped YES outcome set. It is not a
  second independently inferred proposition.
- For the current soccer 1X2 distribution, a contract equivalent to “Home wins in
  regulation” may be represented by HOME for YES and DRAW plus AWAY for NO. A
  “wins by two or more goals” contract is not representable by 1X2; it remains
  unmapped unless a supported score distribution and matching settlement rules
  are available.
- If equivalence or settlement semantics are ambiguous, retain the venue-native
  contract as unmapped. Do not infer mappings from labels, prices, ticker text or
  approximate semantic similarity. This ADR defines an eligibility boundary,
  not a mapping-write workflow or a general proposition language.

### Local inspection API

- Add an opt-in, read-only endpoint for the one authored Kalshi fixture so the
  exact bid ladders and provenance can be inspected through the API contract.
- Identify it with the provider source and source-scoped ticker. Return the
  provider-neutral binary bid levels, separate source and venue, simulated
  snapshot timestamp, raw checksum/size, parser/normalizer versions,
  `SYNTHETIC_ONLY`, unknown historical availability, and explicit
  `UNMAPPED` status. Do not return raw payload bytes or imply canonical identity.
- The default application remains unconfigured and returns 503 for this read.
  Only an explicit local fixture factory configures it. Keep the operator command
  bound to loopback with proxy-header trust disabled; no hosted, LAN, tunnel or
  external exposure is authorized.
- Re-read/re-verify the authored bytes on each request through the existing
  retained-capture normalizer. Use no database, S3, provider network, credentials,
  writes, authentication changes, live acquisition or persistence.
- Add only GET. An unknown source/ticker returns 404; a missing or invalid
  configured fixture fails closed as a sanitized 503. Responses use
  `Cache-Control: no-store`.

This diagnostic endpoint is deliberately independent of canonical market/quote
reads. It does not enable price conversion, probability, EV, trading, model inputs,
backtesting, or eligibility. Future live or mapped order-book APIs require another
review and decision.

## Consequences

The local API can exercise generated OpenAPI/client contracts while the authored
fixture remains visibly synthetic and unmapped. It does not solve canonical
proposition persistence or mapping review. The narrow mapping rule supports exact
outcome-derived propositions and intentionally rejects contracts requiring richer
score, timing, player, or special settlement semantics that the active model cannot
represent.

## Validation

Tests must prove default unconfigured behavior, exact fixture replay and decimal
serialization, source/venue distinction, no-store headers, unknown ticker
handling, sanitized retained-data failures, GET-only behavior and unchanged
canonical market reads. Regenerate OpenAPI and its TypeScript client from the
authoritative FastAPI application. Routine checks remain offline. No real provider
contract call or production deployment is part of this decision.
