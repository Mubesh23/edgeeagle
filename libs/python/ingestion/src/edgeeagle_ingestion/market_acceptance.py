"""Inward-owned transactional quote acceptance contract and stable receipt identity."""

import hashlib
import json
from typing import Protocol

from edgeeagle_domain._validation import instance
from edgeeagle_domain.sports import EventId
from edgeeagle_ingestion.market_receipts import decode_market_receipt, encode_market_receipt
from edgeeagle_ingestion.synthetic_markets import MarketCandidate, MarketFixtureBinding


class MarketAcceptanceConflict(Exception):
    """Existing references or retained projection differ; never overwrite them."""


def receipt_id(candidate: MarketCandidate) -> str:
    instance(candidate, MarketCandidate, "candidate")
    body = json.dumps(
        {"identity_version": 1, "quote_ids": sorted(q.quote_id.value for q in candidate.quotes)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(body).hexdigest()


def canonical_batch(candidates: tuple[MarketCandidate, ...]) -> tuple[MarketCandidate, ...]:
    """Structural coverage; raw replay must precede acceptance in application composition."""
    instance(candidates, tuple, "candidates")
    if not 1 <= len(candidates) <= 2000:
        raise ValueError("acceptance requires a bounded nonempty capture")
    values = tuple(decode_market_receipt(encode_market_receipt(c)) for c in candidates)
    bindings: dict[str, MarketFixtureBinding] = {}
    books: dict[str, set[str]] = {}
    event_ids: dict[EventId, str] = {}
    for c in values:
        if c.raw != values[0].raw:
            raise ValueError("acceptance cannot mix captures")
        key = c.binding.event.key.provider_entity_id
        if key in bindings and bindings[key] != c.binding:
            raise ValueError("conflicting event bindings")
        if c.market.event_id in event_ids and event_ids[c.market.event_id] != key:
            raise ValueError("collapsed canonical event identity")
        event_ids[c.market.event_id] = key
        bindings[key] = c.binding
        seen = books.setdefault(key, set())
        if c.bookmaker in seen:
            raise ValueError("duplicate market candidate")
        seen.add(c.bookmaker)
    if len(bindings) > 100 or any(
        books[key] != {v.provider_key for v in binding.venues} for key, binding in bindings.items()
    ):
        raise ValueError("incomplete or oversized binding coverage")
    return tuple(sorted(values, key=lambda c: (c.market.event_id.value, receipt_id(c))))


class MarketAcceptanceRepository(Protocol):
    def accept(self, candidates: tuple[MarketCandidate, ...]) -> int:
        """Atomically accept one normalized capture; return newly inserted receipt count."""
        ...

    def get(self, identity: str) -> MarketCandidate | None:
        """Return validated retained receipt/projection, not current reference context."""
        ...
