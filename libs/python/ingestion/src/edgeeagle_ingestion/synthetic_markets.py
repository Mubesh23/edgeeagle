"""Bounded authored market adapter, not a live provider contract or price evaluator."""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, NoReturn

from edgeeagle_domain._validation import aware_datetime, instance, text
from edgeeagle_domain.consistency import validate_event_context
from edgeeagle_domain.markets import (
    Market,
    MarketPeriod,
    MarketType,
    Outcome,
    Quote,
    QuoteId,
    Selection,
    validate_market_selections,
)
from edgeeagle_domain.provenance import DataSource, Venue, VenueType
from edgeeagle_domain.raw import RawPayloadIntegrityError, RawPayloadReference, RawPayloadStore
from edgeeagle_domain.sports import Event, EventParticipant
from edgeeagle_ingestion.identity import lineage_json_value
from edgeeagle_ingestion.synthetic_events import FixtureEventBinding

PARSER_VERSION = "synthetic-market-json-v1"
NORMALIZER_VERSION = "synthetic-market-bindings-v1"
MAX_BYTES = 1024 * 1024


def replay_market_fixture(
    store: RawPayloadStore, candidates: tuple["MarketCandidate", ...]
) -> tuple["MarketCandidate", ...]:
    """Reproduce a complete capture using retained bindings, never current mappings."""
    instance(candidates, tuple, "candidates")
    if not candidates or len(candidates) > 2000:
        raise ValueError("replay requires a bounded complete capture")
    bindings: dict[str, MarketFixtureBinding] = {}
    seen = set()
    for candidate in candidates:
        instance(candidate, MarketCandidate, "candidate")
        if candidate.raw != candidates[0].raw:
            raise ValueError("replay cannot mix raw captures")
        key = candidate.binding.event.key.provider_entity_id
        if key in bindings and bindings[key] != candidate.binding:
            raise ValueError("conflicting retained event bindings")
        bindings[key] = candidate.binding
        identity = (key, candidate.bookmaker)
        if identity in seen:
            raise ValueError("duplicate replay candidate")
        seen.add(identity)
    result = normalize_market_fixture(store, candidates[0].raw, tuple(bindings.values()))
    if set(result) != set(candidates):
        raise ValueError("retained market projection differs from replay")
    return result


@dataclass(frozen=True, kw_only=True)
class VenueBinding:
    provider_key: str
    venue: Venue

    def __post_init__(self) -> None:
        text(self.provider_key, "provider_key")
        instance(self.venue, Venue, "venue")
        if self.venue.venue_type is not VenueType.SPORTSBOOK:
            raise ValueError("fixture prices require a sportsbook venue")


@dataclass(frozen=True, kw_only=True)
class MarketFixtureBinding:
    event: FixtureEventBinding
    starts_at: datetime
    source: DataSource
    venues: tuple[VenueBinding, ...]

    def __post_init__(self) -> None:
        instance(self.event, FixtureEventBinding, "event")
        instance(self.source, DataSource, "source")
        instance(self.venues, tuple, "venues")
        aware_datetime(self.starts_at, "starts_at")
        object.__setattr__(self, "starts_at", self.starts_at.astimezone(UTC))
        if "SYNTHETIC_FIXTURE" not in self.source.capabilities:
            raise ValueError("source must explicitly declare SYNTHETIC_FIXTURE")
        b = self.event
        if self.source.data_source_id != b.key.data_source_id:
            raise ValueError("binding source mismatch")
        if b.sport.code != "soccer" or any(p.participant_type != "TEAM" for p in (b.home, b.away)):
            raise ValueError("fixture requires soccer TEAM context")
        if len({b.home_label, b.away_label, "Draw"}) != 3:
            raise ValueError("ambiguous outcome labels")
        if not 1 <= len(self.venues) <= 20:
            raise ValueError("binding requires 1..20 venues")
        for venue in self.venues:
            instance(venue, VenueBinding, "venue binding")
        if len({v.provider_key for v in self.venues}) != len(self.venues) or len(
            {v.venue.venue_id for v in self.venues}
        ) != len(self.venues):
            raise ValueError("duplicate or collapsed venue bindings")
        validate_event_context(
            event=self.canonical_event,
            sport=b.sport,
            competition=b.competition,
            season=b.season,
            participants=(b.home, b.away),
            entries=self.entries,
        )

    @property
    def canonical_event(self) -> Event:
        b = self.event
        return Event(
            event_id=b.event_id,
            sport_id=b.sport.sport_id,
            competition_id=b.competition.competition_id,
            season_id=b.season.season_id,
            starts_at=self.starts_at,
            status=b.status,
        )

    @property
    def entries(self) -> tuple[EventParticipant, ...]:
        return tuple(
            EventParticipant(
                event_id=self.event.event_id, participant_id=p.participant_id, role=role
            )
            for p, role in ((self.event.home, "HOME"), (self.event.away, "AWAY"))
        )


def quote_identity(
    raw: RawPayloadReference, binding: MarketFixtureBinding, bookmaker: str, outcome_label: str
) -> QuoteId:
    """Price/output excluded: changed projection under identical lineage must conflict."""
    fields = {
        "identity_version": 1,
        "raw": asdict(raw),
        "provider_event_key": asdict(binding.event.key),
        "bookmaker": bookmaker,
        "market": "h2h",
        "outcome": outcome_label,
        "parser_version": PARSER_VERSION,
        "normalizer_version": NORMALIZER_VERSION,
        "context_version": binding.event.context_version,
    }
    wire = json.dumps(fields, default=lineage_json_value, sort_keys=True, separators=(",", ":"))
    return QuoteId(hashlib.sha256(wire.encode("ascii")).hexdigest())


@dataclass(frozen=True, kw_only=True)
class MarketCandidate:
    raw: RawPayloadReference
    binding: MarketFixtureBinding
    bookmaker: str
    market: Market
    selections: tuple[Selection, ...]
    quotes: tuple[Quote, ...]

    def __post_init__(self) -> None:
        instance(self.raw, RawPayloadReference, "raw")
        instance(self.binding, MarketFixtureBinding, "binding")
        text(self.bookmaker, "bookmaker")
        instance(self.quotes, tuple, "quotes")
        validate_market_selections(self.market, self.selections, self.binding.entries)
        venues = {v.provider_key: v.venue.venue_id for v in self.binding.venues}
        if (
            self.bookmaker not in venues
            or self.raw.capture.data_source_id != self.binding.source.data_source_id
        ):
            raise ValueError("candidate source/venue mismatch")
        if len(self.quotes) != 3:
            raise ValueError("candidate must contain three quotes")
        labels = {
            Outcome.HOME: self.binding.event.home_label,
            Outcome.AWAY: self.binding.event.away_label,
            Outcome.DRAW: "Draw",
        }
        selected = {s.selection_id: s for s in self.selections}
        seen = set()
        for q in self.quotes:
            instance(q, Quote, "quote")
            if q.selection_id not in selected or q.selection_id in seen:
                raise ValueError("quote selection mismatch/duplicate")
            seen.add(q.selection_id)
            if (
                q.data_source_id != self.raw.capture.data_source_id
                or q.venue_id != venues[self.bookmaker]
                or q.ingested_at != self.raw.capture.ingested_at
                or q.available_at != self.raw.capture.available_at
                or q.effective_at != self.raw.capture.effective_at
                or q.provider_quote_id is not None
                or q.quote_id
                != quote_identity(
                    self.raw, self.binding, self.bookmaker, labels[selected[q.selection_id].outcome]
                )
            ):
                raise ValueError("quote lineage mismatch")


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _constant(value: str) -> NoReturn:
    raise ValueError("nonstandard JSON number")


def _timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be ISO text")
    result = datetime.fromisoformat(value)
    aware_datetime(result, "timestamp")
    return result.astimezone(UTC)


def _list(value: object, low: int, high: int) -> list[Any]:
    if not isinstance(value, list) or not low <= len(value) <= high:
        raise ValueError("invalid fixture collection size")
    return value


def normalize_market_fixture(
    store: RawPayloadStore, raw: RawPayloadReference, bindings: tuple[MarketFixtureBinding, ...]
) -> tuple[MarketCandidate, ...]:
    """Read retained bytes once, validate the whole capture, return no partial prefix."""
    instance(raw, RawPayloadReference, "raw")
    instance(bindings, tuple, "bindings")
    if raw.size_bytes > MAX_BYTES or not 1 <= len(bindings) <= 100:
        raise ValueError("fixture bounds exceeded")
    for binding in bindings:
        instance(binding, MarketFixtureBinding, "binding")
    by_id = {b.event.key.provider_entity_id: b for b in bindings}
    if len(by_id) != len(bindings) or len({b.event.event_id for b in bindings}) != len(bindings):
        raise ValueError("duplicate or collapsed event bindings")
    body = store.get(raw)
    if body is None:
        raise FileNotFoundError("retained market fixture is missing")
    if len(body) != raw.size_bytes or hashlib.sha256(body).hexdigest() != raw.sha256:
        raise RawPayloadIntegrityError("market fixture differs from raw reference")
    try:
        rows = _list(
            json.loads(
                body,
                object_pairs_hook=_object,
                parse_float=Decimal,
                parse_int=Decimal,
                parse_constant=_constant,
            ),
            1,
            100,
        )
        seen = set()
        results = []
        for row in rows:
            key = row["id"]
            if key in seen or key not in by_id:
                raise ValueError("duplicate or unbound event")
            seen.add(key)
            b = by_id[key]
            if (
                row["sport_key"],
                row["home_team"],
                row["away_team"],
                _timestamp(row["commence_time"]),
            ) != (b.event.competition_key, b.event.home_label, b.event.away_label, b.starts_at):
                raise ValueError("event binding guards mismatch")
            market = Market(
                event_id=b.event.event_id,
                market_type=MarketType.RESULT_3WAY,
                period=MarketPeriod.REGULATION_TIME,
            )
            outcomes = {
                b.event.home_label: (Outcome.HOME, b.event.home.participant_id),
                "Draw": (Outcome.DRAW, None),
                b.event.away_label: (Outcome.AWAY, b.event.away.participant_id),
            }
            venues = {v.provider_key: v.venue.venue_id for v in b.venues}
            seen_books = set()
            for book in _list(row["bookmakers"], 1, 20):
                bk = book["key"]
                if bk not in venues or bk in seen_books:
                    raise ValueError("unbound or duplicate bookmaker")
                seen_books.add(bk)
                native_market = _list(book["markets"], 1, 1)[0]
                if native_market["key"] != "h2h":
                    raise ValueError("unsupported market")
                observed = (
                    _timestamp(native_market["last_update"])
                    if native_market.get("last_update") is not None
                    else None
                )
                selected, quotes, seen_outcomes = [], [], set()
                for native in _list(native_market["outcomes"], 3, 3):
                    label, price = native["name"], native["price"]
                    if (
                        label not in outcomes
                        or label in seen_outcomes
                        or not isinstance(price, Decimal)
                    ):
                        raise ValueError("invalid or duplicate outcome/price")
                    seen_outcomes.add(label)
                    outcome, participant = outcomes[label]
                    selection = Selection(
                        market_id=market.market_id, outcome=outcome, participant_id=participant
                    )
                    selected.append(selection)
                    quotes.append(
                        Quote(
                            quote_id=quote_identity(raw, b, bk, label),
                            selection_id=selection.selection_id,
                            data_source_id=raw.capture.data_source_id,
                            venue_id=venues[bk],
                            odds_decimal=price,
                            observed_at=observed,
                            ingested_at=raw.capture.ingested_at,
                            available_at=raw.capture.available_at,
                            effective_at=raw.capture.effective_at,
                        )
                    )
                results.append(
                    MarketCandidate(
                        raw=raw,
                        binding=b,
                        bookmaker=bk,
                        market=market,
                        selections=tuple(sorted(selected, key=lambda s: s.selection_id.value)),
                        quotes=tuple(sorted(quotes, key=lambda q: q.quote_id.value)),
                    )
                )
            if seen_books != set(venues):
                raise ValueError("incomplete venue coverage")
        if seen != set(by_id):
            raise ValueError("incomplete event coverage")
        return tuple(sorted(results, key=lambda c: (c.market.market_id.value, c.bookmaker)))
    except (KeyError, TypeError, AttributeError, UnicodeError, RecursionError) as exc:
        raise ValueError("malformed market fixture") from exc
