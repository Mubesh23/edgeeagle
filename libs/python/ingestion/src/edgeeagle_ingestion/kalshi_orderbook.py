"""Offline parser for retained Kalshi fixed-point binary order-book fixtures."""

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, NoReturn

from edgeeagle_domain._validation import aware_datetime, instance
from edgeeagle_domain.markets import BinaryOrderBook, OrderBookLevel
from edgeeagle_domain.provenance import DataSourceId, VenueId
from edgeeagle_domain.raw import RawPayloadIntegrityError, RawPayloadReference, RawPayloadStore

PARSER_VERSION = "kalshi-orderbook-json-v1"
NORMALIZER_VERSION = "kalshi-binary-orderbook-v1"
MAX_BYTES = 1024 * 1024
_TICKER = re.compile(r"[A-Z0-9][A-Z0-9_-]{0,127}\Z")
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")


@dataclass(frozen=True, kw_only=True)
class KalshiOrderBookManifest:
    """Retained response binding; the payload itself omits ticker and snapshot time."""

    raw: RawPayloadReference
    market_ticker: str
    venue_id: VenueId
    simulated_snapshot_at: datetime

    def __post_init__(self) -> None:
        instance(self.raw, RawPayloadReference, "raw")
        instance(self.venue_id, VenueId, "venue_id")
        if not isinstance(self.market_ticker, str) or not _TICKER.fullmatch(self.market_ticker):
            raise ValueError("market_ticker must be a bounded uppercase provider ticker")
        if self.raw.size_bytes > MAX_BYTES:
            raise ValueError("Kalshi order-book capture exceeds 1 MiB")
        if self.raw.capture.resource != self.endpoint:
            raise ValueError("raw capture resource does not match bound market ticker")
        if any(
            value is not None
            for value in (
                self.raw.capture.effective_at,
                self.raw.capture.observed_at,
                self.raw.capture.available_at,
            )
        ):
            raise ValueError("this fixture path requires unknown provider event-time evidence")
        aware_datetime(self.simulated_snapshot_at, "simulated_snapshot_at")
        object.__setattr__(
            self, "simulated_snapshot_at", self.simulated_snapshot_at.astimezone(UTC)
        )

    @property
    def endpoint(self) -> str:
        return f"/trade-api/v2/markets/{self.market_ticker}/orderbook"


@dataclass(frozen=True, kw_only=True)
class KalshiOrderBookCandidate:
    """Parsed projection with immutable lineage; not a canonical market or quote."""

    manifest: KalshiOrderBookManifest
    order_book: BinaryOrderBook

    def __post_init__(self) -> None:
        instance(self.manifest, KalshiOrderBookManifest, "manifest")
        instance(self.order_book, BinaryOrderBook, "order_book")

    @property
    def raw(self) -> RawPayloadReference:
        return self.manifest.raw

    @property
    def market_ticker(self) -> str:
        return self.manifest.market_ticker

    @property
    def data_source_id(self) -> DataSourceId:
        return self.raw.capture.data_source_id

    @property
    def venue_id(self) -> VenueId:
        return self.manifest.venue_id

    @property
    def snapshot_at(self) -> datetime:
        return self.manifest.simulated_snapshot_at

    @property
    def parser_version(self) -> str:
        return PARSER_VERSION

    @property
    def normalizer_version(self) -> str:
        return NORMALIZER_VERSION

    @property
    def usage(self) -> str:
        return "SYNTHETIC_ONLY"


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _forbid_number(value: str) -> NoReturn:
    raise ValueError(f"JSON numeric value is unsupported: {value}")


def _constant(value: str) -> NoReturn:
    raise ValueError(f"nonstandard JSON number is unsupported: {value}")


def _levels(value: object, side: str) -> tuple[OrderBookLevel, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{side} must be an array")
    result = []
    for pair in value:
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError(f"each {side} level must contain exactly price and size")
        price_text, count_text = pair
        if not isinstance(price_text, str) or not isinstance(count_text, str):
            raise ValueError(f"{side} price and size must be decimal strings")
        if not _DECIMAL.fullmatch(price_text) or not _DECIMAL.fullmatch(count_text):
            raise ValueError(f"{side} contains a malformed fixed-point decimal")
        try:
            result.append(
                OrderBookLevel(
                    price_dollars=Decimal(price_text), contract_count=Decimal(count_text)
                )
            )
        except (InvalidOperation, TypeError, ValueError) as error:
            raise ValueError(f"invalid {side} level") from error
    levels = tuple(result)
    # The provider's wire contract is ascending. Domain values preserve and verify it.
    BinaryOrderBook(
        yes_bids=levels if side == "YES" else (), no_bids=levels if side == "NO" else ()
    )
    return levels


def _parse(body: bytes) -> BinaryOrderBook:
    try:
        document = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=_object,
            parse_float=_forbid_number,
            parse_int=_forbid_number,
            parse_constant=_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
        raise ValueError("Kalshi order-book payload must be UTF-8 JSON") from error
    if not isinstance(document, dict) or set(document) != {"orderbook_fp"}:
        raise ValueError("unsupported Kalshi order-book response fields")
    fixed = document["orderbook_fp"]
    if not isinstance(fixed, dict) or set(fixed) != {"yes_dollars", "no_dollars"}:
        raise ValueError("unsupported Kalshi fixed-point order-book fields")
    return BinaryOrderBook(
        yes_bids=_levels(fixed["yes_dollars"], "YES"),
        no_bids=_levels(fixed["no_dollars"], "NO"),
    )


def normalize_kalshi_orderbook(
    store: RawPayloadStore, manifest: KalshiOrderBookManifest
) -> KalshiOrderBookCandidate:
    """Read and verify retained bytes, then return one complete order-book projection."""
    instance(manifest, KalshiOrderBookManifest, "manifest")
    body = store.get(manifest.raw)
    if body is None:
        raise FileNotFoundError("retained Kalshi order-book fixture is missing")
    if (
        len(body) != manifest.raw.size_bytes
        or hashlib.sha256(body).hexdigest() != manifest.raw.sha256
    ):
        raise RawPayloadIntegrityError("retained Kalshi order-book differs from manifest")
    if len(body) > MAX_BYTES:
        raise ValueError("Kalshi order-book capture exceeds 1 MiB")
    return KalshiOrderBookCandidate(manifest=manifest, order_book=_parse(body))


def replay_kalshi_orderbook(
    store: RawPayloadStore, candidate: KalshiOrderBookCandidate
) -> KalshiOrderBookCandidate:
    """Reparse exact retained context and reject any projection that has drifted."""
    instance(candidate, KalshiOrderBookCandidate, "candidate")
    replayed = normalize_kalshi_orderbook(store, candidate.manifest)
    if replayed != candidate:
        raise RawPayloadIntegrityError("retained Kalshi order-book projection differs from replay")
    return replayed
