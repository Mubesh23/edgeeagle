"""Parameterized market reads with bounded pages and retained quote provenance."""

from sqlalchemy import Connection, text

from edgeeagle_domain._validation import instance
from edgeeagle_domain.market_query import (
    MarketPage,
    MarketQuery,
    MarketView,
    QuoteObservation,
    QuotePage,
    QuoteQuery,
)
from edgeeagle_domain.markets import (
    Market,
    MarketId,
    MarketPeriod,
    MarketType,
    Outcome,
    Selection,
    validate_market_selections,
)
from edgeeagle_domain.sports import EventId, EventParticipant, ParticipantId
from edgeeagle_ingestion.market_acceptance import MarketAcceptanceConflict
from edgeeagle_ingestion.synthetic_markets import (
    NORMALIZER_VERSION,
    PARSER_VERSION,
    MarketCandidate,
)
from edgeeagle_persistence._transactions import require_transaction
from edgeeagle_persistence.markets import PostgresMarketAcceptanceRepository


class PostgresMarketReader:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def _snapshot(self) -> None:
        require_transaction(self._connection)
        if self._connection.get_isolation_level() != "REPEATABLE READ":
            raise ValueError("market reads require REPEATABLE READ")
        if self._connection.scalar(text("SHOW transaction_read_only")) != "on":
            raise ValueError("market reads require READ ONLY")

    def list_markets(self, event_id: EventId, query: MarketQuery) -> MarketPage | None:
        instance(event_id, EventId, "event_id")
        instance(query, MarketQuery, "query")
        self._snapshot()
        if not self._connection.scalar(
            text("SELECT EXISTS (SELECT 1 FROM events WHERE event_id = :id)"),
            {"id": event_id.value},
        ):
            return None
        rows = (
            self._connection.execute(
                text(
                    "SELECT market_id, market_type, period FROM markets WHERE event_id = :id "
                    + ("AND market_id > :after " if query.after_market_id else "")
                    + "ORDER BY market_id LIMIT :count"
                ),
                {
                    "id": event_id.value,
                    "after": query.after_market_id.value if query.after_market_id else None,
                    "count": query.limit + 1,
                },
            )
            .mappings()
            .all()
        )
        items = []
        for row in rows[: query.limit]:
            market = Market(
                event_id=event_id,
                market_type=MarketType(row["market_type"]),
                period=MarketPeriod(row["period"]),
            )
            if market.market_id.value != row["market_id"]:
                raise MarketAcceptanceConflict("Stored market identity differs from semantics")
            native = (
                self._connection.execute(
                    text(
                        "SELECT selection_id, outcome, participant_id FROM market_selections "
                        "WHERE market_id = :id ORDER BY selection_id"
                    ),
                    {"id": row["market_id"]},
                )
                .mappings()
                .all()
            )
            selections = tuple(
                Selection(
                    market_id=market.market_id,
                    outcome=Outcome(s["outcome"]),
                    participant_id=ParticipantId(s["participant_id"])
                    if s["participant_id"]
                    else None,
                )
                for s in native
            )
            if any(
                s.selection_id.value != r["selection_id"]
                for s, r in zip(selections, native, strict=True)
            ):
                raise MarketAcceptanceConflict("Stored selection identity differs from semantics")
            # Validate retained membership, not mutable current event roles/names.
            entries = tuple(
                EventParticipant(
                    event_id=event_id, participant_id=s.participant_id, role=s.outcome.value
                )
                for s in selections
                if s.participant_id is not None
            )
            validate_market_selections(market, selections, entries)
            items.append(MarketView(market, selections))
        return MarketPage(
            tuple(items), items[-1].market.market_id if len(rows) > query.limit else None
        )

    def list_quotes(self, market_id: MarketId, query: QuoteQuery) -> QuotePage | None:
        instance(market_id, MarketId, "market_id")
        instance(query, QuoteQuery, "query")
        self._snapshot()
        if not self._connection.scalar(
            text("SELECT EXISTS (SELECT 1 FROM markets WHERE market_id = :id)"),
            {"id": market_id.value},
        ):
            return None
        rows = (
            self._connection.execute(
                text(
                    "SELECT quote_id, receipt_id FROM market_quotes WHERE market_id = :id "
                    + ("AND quote_id > :after " if query.after_quote_id else "")
                    + "ORDER BY quote_id LIMIT :count"
                ),
                {
                    "id": market_id.value,
                    "after": query.after_quote_id.value if query.after_quote_id else None,
                    "count": query.limit + 1,
                },
            )
            .mappings()
            .all()
        )
        receipts: dict[str, MarketCandidate] = {}
        repository = PostgresMarketAcceptanceRepository(self._connection)
        items = []
        for row in rows[: query.limit]:
            identity = row["receipt_id"]
            if identity not in receipts:
                candidate = repository.get(identity)
                if candidate is None or candidate.market.market_id != market_id:
                    raise MarketAcceptanceConflict("Quote receipt is missing or mismatched")
                receipts[identity] = candidate
            retained = receipts[identity]
            quote = next((q for q in retained.quotes if q.quote_id.value == row["quote_id"]), None)
            if quote is None:
                raise MarketAcceptanceConflict("Quote is absent from retained receipt")
            selection = next(s for s in retained.selections if s.selection_id == quote.selection_id)
            labels = {
                Outcome.HOME: retained.binding.event.home_label,
                Outcome.AWAY: retained.binding.event.away_label,
                Outcome.DRAW: "Draw",
            }
            items.append(
                QuoteObservation(
                    quote=quote,
                    market_id=market_id,
                    receipt_id=identity,
                    raw=retained.raw,
                    provider_event_id=retained.binding.event.key.provider_entity_id,
                    provider_bookmaker_key=retained.bookmaker,
                    provider_market_key="h2h",
                    provider_outcome_label=labels[selection.outcome],
                    parser_version=PARSER_VERSION,
                    normalizer_version=NORMALIZER_VERSION,
                    context_version=retained.binding.event.context_version,
                    usage="SYNTHETIC_ONLY",
                )
            )
        return QuotePage(
            tuple(items), items[-1].quote.quote_id if len(rows) > query.limit else None
        )
