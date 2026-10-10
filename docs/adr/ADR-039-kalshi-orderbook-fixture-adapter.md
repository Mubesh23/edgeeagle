# ADR-039 — Fixture-first Kalshi public order-book adapter

**Status:** Proposed for the bounded offline adapter slice  
**Date:** 2026-10-09

## Context

Phase 3 includes Kalshi market-data support, while the current market domain and
quote persistence implement decimal sportsbook prices for a canonical soccer
three-way result. A Kalshi binary contract order book is not that shape. The
public Kalshi order-book response has YES and NO bid levels; asks are omitted
because a bid on one side is complementary to an ask on the other. Treating those
levels as decimal odds or ordinary `Quote` records would erase contract semantics.

Kalshi's current public `GET /markets/{ticker}/orderbook` endpoint does not require
authentication. Its fixed-point response contains `orderbook_fp.yes_dollars` and
`no_dollars` arrays of `[price_dollars, contract_count]` strings. Prices and sizes
may use fractional precision; each side is ordered ascending by price. The endpoint
does not include the requested market ticker or a provider observation timestamp
in this response. Current contract notes and source links are maintained in the
[provider evaluation](../data/provider-evaluation.md#kalshi-public-order-book-contract-review).

## Decision

Add an offline, fixture-first ingestion adapter for one retained Kalshi market
order-book response. Reuse the shared raw capture/store boundary and add only the
small provider-neutral binary-order-book value required to preserve the response:

- source and venue remain separate (`KALSHI_API` and `KALSHI`);
- the source-scoped Kalshi market ticker is retained as a provider locator, not a
  canonical `MarketId`;
- YES and NO bid levels retain exact Decimal dollar prices and contract counts,
  including their input order;
- raw reference/checksum/size and parser/normalizer versions remain available to
  replay and audit the normalized result;
- capture/ingestion clocks are explicit; `available_at` remains unknown, and an
  authored fixture is `SYNTHETIC_ONLY`.

The supported parser profile is only `orderbook_fp` with exact two-string levels
under `yes_dollars` and `no_dollars`. Bound raw input to 1 MiB, reject duplicate
JSON keys, non-standard JSON numbers, floats/numeric JSON values, booleans, unknown
structural fields, malformed decimals, out-of-range binary prices, nonpositive
contract counts, duplicate price levels, non-ascending level order, and missing or
extra tuple items. Empty books are valid. Parsing returns no partial result.

The initial adapter reads only authored retained fixtures. It makes no HTTP
requests, uses no credentials, and provides no live acquisition, event discovery,
market creation, persistence, API, execution, price conversion, implied
probability, tradeability, or backtest eligibility. Fixture bindings provide an
explicit market ticker and capture metadata because the order-book payload itself
does not include those values. Their consistency is guarded against the retained
capture reference, not independently verified provider identity.

## Canonical mapping boundary

The provider-neutral snapshot value is not a canonical event/market assignment.
No current domain contract represents arbitrary binary propositions or YES/NO
selections. Therefore this slice must not attach an order book to a soccer event,
reuse `MarketType.RESULT_3WAY`, or publish it through the canonical quote API.
Canonical event/market mapping, supported proposition types, bid/ask derivation,
crossed-book policy, quote/model integration, and historical eligibility need a
separate decision before they are added. Raw provider text and rules are not
interpreted as canonical semantics.

## Validation and rollout

1. Add the ADR, provider-contract verification note, roadmap pointer and index link.
2. Add immutable provider-neutral binary order-book values to the domain with
   explicit validation for side, exact decimal price, positive size and ordered
   levels.
3. Add the ingestion parser/normalizer and retained-context replay; pin a
   provider-shaped authored fixture and cover empty sides, fractional precision,
   malformed/duplicate keys, invalid prices/sizes, out-of-order/duplicate levels,
   wrong ticker context, corruption, unsupported structure and replay drift.
4. Keep routine validation network-free. No Kalshi contract test is added to
   `scripts/validate`; public endpoint validation remains an explicit future tier.
5. Run the relevant package tests and build. Run full `scripts/validate` when the
   existing dependency-security gate is clear; otherwise report that independent
   blocker without suppressing or waiving it.

This ADR authorizes no live capture, API change, schema migration or trade path.
