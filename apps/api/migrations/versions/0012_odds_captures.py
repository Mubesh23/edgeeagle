"""Add retained provider captures without altering legacy synthetic receipt guards."""

from alembic import op

revision = "0012_odds_captures"
down_revision = "0011_market_quotes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE odds_capture_receipts (
            capture_id text COLLATE "C" PRIMARY KEY CHECK (capture_id ~ '^[0-9a-f]{64}$'),
            data_source_id text COLLATE "C" NOT NULL REFERENCES data_sources(data_source_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            snapshot text NOT NULL CHECK (octet_length(snapshot) BETWEEN 1 AND 8388608),
            CHECK ((snapshot::jsonb->'format' = '2'::jsonb AND
                snapshot::jsonb->>'usage' IN ('SYNTHETIC_ONLY', 'REPLAY_ONLY') AND
                snapshot::jsonb#>>'{capture,parser_version}' = 'the-odds-api-soccer-h2h-json-v1' AND
                snapshot::jsonb#>>'{capture,normalizer_version}' =
                    'the-odds-api-soccer-h2h-normalization-v1' AND
                snapshot::jsonb#>>'{capture,manifest,raw,capture,data_source_id,value}' =
                    data_source_id AND
                ((snapshot::jsonb->>'usage' = 'SYNTHETIC_ONLY' AND
                  snapshot::jsonb#>>'{capture,manifest,origin}' = 'AUTHORED_FIXTURE') OR
                 (snapshot::jsonb->>'usage' = 'REPLAY_ONLY' AND
                  snapshot::jsonb#>>'{capture,manifest,origin}' = 'PROVIDER_CAPTURE'))
            ) IS TRUE),
            UNIQUE (capture_id, data_source_id)
        )
    """)
    op.execute("""
        CREATE TABLE odds_capture_quotes (
            quote_id text COLLATE "C" PRIMARY KEY CHECK (quote_id ~ '^[0-9a-f]{64}$'),
            capture_id text COLLATE "C" NOT NULL,
            selection_id text COLLATE "C" NOT NULL,
            market_id text COLLATE "C" NOT NULL REFERENCES markets(market_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            data_source_id text COLLATE "C" NOT NULL,
            venue_id text COLLATE "C" NOT NULL REFERENCES venues(venue_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            odds_decimal numeric NOT NULL CHECK (odds_decimal > 1 AND odds_decimal < 'Infinity'),
            ingested_at timestamptz NOT NULL CHECK (isfinite(ingested_at)),
            observed_at timestamptz CHECK (observed_at IS NULL OR isfinite(observed_at)),
            FOREIGN KEY (selection_id, market_id)
                REFERENCES market_selections(selection_id, market_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            FOREIGN KEY (capture_id, data_source_id)
                REFERENCES odds_capture_receipts(capture_id, data_source_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            UNIQUE (capture_id, selection_id, venue_id)
        )
    """)
    for name, table, columns in (
        ("ix_odds_capture_source", "odds_capture_receipts", "data_source_id"),
        ("ix_odds_quotes_page", "odds_capture_quotes", "market_id, quote_id"),
        ("ix_odds_quotes_selection", "odds_capture_quotes", "selection_id, market_id"),
        ("ix_odds_quotes_venue", "odds_capture_quotes", "venue_id"),
    ):
        op.execute(f"CREATE INDEX {name} ON {table} ({columns})")
    for table in ("odds_capture_receipts", "odds_capture_quotes"):
        op.execute(f"""
            CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON {table}
            FOR EACH STATEMENT EXECUTE FUNCTION edgeeagle_market_immutable()
        """)


def downgrade() -> None:
    op.execute("LOCK TABLE odds_capture_receipts, odds_capture_quotes IN ACCESS EXCLUSIVE MODE")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM odds_capture_receipts) THEN
                RAISE EXCEPTION 'Cannot downgrade with retained Odds API captures';
            END IF;
        END $$;
    """)
    op.drop_table("odds_capture_quotes")
    op.drop_table("odds_capture_receipts")
