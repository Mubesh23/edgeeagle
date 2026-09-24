"""Add immutable canonical markets, selections, quote observations and receipts."""

from alembic import op

revision = "0011_market_quotes"
down_revision = "0010_soccer_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE markets (
            market_id text COLLATE "C" PRIMARY KEY CHECK (market_id ~ '^[0-9a-f]{64}$'),
            event_id text COLLATE "C" NOT NULL REFERENCES events(event_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            market_type text NOT NULL CHECK (market_type = 'RESULT_3WAY'),
            period text NOT NULL CHECK (period = 'REGULATION_TIME'),
            UNIQUE (event_id, market_type, period)
        )
    """)
    op.execute("""
        CREATE TABLE market_selections (
            selection_id text COLLATE "C" PRIMARY KEY CHECK (selection_id ~ '^[0-9a-f]{64}$'),
            market_id text COLLATE "C" NOT NULL REFERENCES markets(market_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            outcome text NOT NULL CHECK (outcome IN ('HOME', 'DRAW', 'AWAY')),
            participant_id text COLLATE "C" REFERENCES participants(participant_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            CHECK ((outcome = 'DRAW') = (participant_id IS NULL)),
            UNIQUE (market_id, outcome),
            UNIQUE (selection_id, market_id)
        )
    """)
    op.execute("""
        CREATE TABLE market_receipts (
            receipt_id text COLLATE "C" PRIMARY KEY CHECK (receipt_id ~ '^[0-9a-f]{64}$'),
            market_id text COLLATE "C" NOT NULL REFERENCES markets(market_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            data_source_id text COLLATE "C" NOT NULL REFERENCES data_sources(data_source_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            venue_id text COLLATE "C" NOT NULL REFERENCES venues(venue_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            snapshot text NOT NULL CHECK (octet_length(snapshot) BETWEEN 1 AND 1048576),
            CHECK ((snapshot::jsonb->'format' = '1'::jsonb AND
                snapshot::jsonb->>'usage' = 'SYNTHETIC_ONLY' AND
                snapshot::jsonb->>'parser_version' = 'synthetic-market-json-v1' AND
                snapshot::jsonb->>'normalizer_version' = 'synthetic-market-bindings-v1' AND
                jsonb_typeof(snapshot::jsonb->'candidate') = 'object' AND
                snapshot::jsonb#>>'{candidate,raw,capture,data_source_id,value}'
                    = data_source_id AND
                snapshot::jsonb#>>'{candidate,binding,source,data_source_id,value}' = data_source_id
            ) IS TRUE),
            UNIQUE (receipt_id, market_id, data_source_id, venue_id)
        )
    """)
    op.execute("""
        CREATE TABLE market_quotes (
            quote_id text COLLATE "C" PRIMARY KEY CHECK (quote_id ~ '^[0-9a-f]{64}$'),
            receipt_id text COLLATE "C" NOT NULL,
            selection_id text COLLATE "C" NOT NULL,
            market_id text COLLATE "C" NOT NULL,
            data_source_id text COLLATE "C" NOT NULL,
            venue_id text COLLATE "C" NOT NULL,
            odds_decimal numeric NOT NULL CHECK (odds_decimal > 1 AND odds_decimal < 'Infinity'),
            ingested_at timestamptz NOT NULL CHECK (isfinite(ingested_at)),
            observed_at timestamptz CHECK (observed_at IS NULL OR isfinite(observed_at)),
            available_at timestamptz CHECK (available_at IS NULL OR isfinite(available_at)),
            effective_at timestamptz CHECK (effective_at IS NULL OR isfinite(effective_at)),
            provider_quote_id text CHECK (provider_quote_id IS NULL),
            CHECK (available_at IS NULL OR available_at <= ingested_at),
            FOREIGN KEY (selection_id, market_id)
                REFERENCES market_selections(selection_id, market_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (receipt_id, market_id, data_source_id, venue_id)
                REFERENCES market_receipts(receipt_id, market_id, data_source_id, venue_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (receipt_id, selection_id)
        )
    """)
    for name, table, columns in (
        ("ix_markets_event_page", "markets", "event_id, market_id"),
        ("ix_selections_participant", "market_selections", "participant_id"),
        ("ix_receipts_market", "market_receipts", "market_id"),
        ("ix_receipts_source", "market_receipts", "data_source_id"),
        ("ix_receipts_venue", "market_receipts", "venue_id"),
        ("ix_quotes_market_page", "market_quotes", "market_id, quote_id"),
        ("ix_quotes_selection", "market_quotes", "selection_id, market_id"),
    ):
        op.execute(f"CREATE INDEX {name} ON {table} ({columns})")
    op.execute("""
        CREATE FUNCTION edgeeagle_market_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION 'Market observations and receipts are immutable'
                USING ERRCODE = '23514';
        END; $$
    """)
    for table in ("markets", "market_selections", "market_receipts", "market_quotes"):
        op.execute(f"""
            CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON {table}
            FOR EACH STATEMENT EXECUTE FUNCTION edgeeagle_market_immutable()
        """)


def downgrade() -> None:
    for table in ("market_quotes", "market_receipts", "market_selections", "markets"):
        op.drop_table(table)
    op.execute("DROP FUNCTION edgeeagle_market_immutable()")
