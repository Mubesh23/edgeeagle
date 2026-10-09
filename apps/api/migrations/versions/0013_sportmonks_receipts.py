"""Add an immutable store for validated Sportmonks observation receipts."""

from alembic import op

revision = "0013_sportmonks_receipts"
down_revision = "0012_odds_captures"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE sportmonks_capture_receipts (
            capture_id text COLLATE "C" PRIMARY KEY CHECK (capture_id ~ '^[0-9a-f]{64}$'),
            data_source_id text COLLATE "C" NOT NULL REFERENCES data_sources(data_source_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            event_id text COLLATE "C" NOT NULL REFERENCES events(event_id)
                ON UPDATE RESTRICT ON DELETE RESTRICT,
            native_fixture_id bigint NOT NULL CHECK (native_fixture_id > 0),
            receipt_format smallint NOT NULL CHECK (receipt_format = 1),
            receipt text NOT NULL CHECK (octet_length(receipt) BETWEEN 1 AND 8388608),
            CONSTRAINT ck_sportmonks_receipt_identity CHECK (
                (receipt::jsonb->'format' = '1'::jsonb AND
                receipt::jsonb->>'usage' IN ('SYNTHETIC_ONLY', 'REPLAY_ONLY') AND
                receipt::jsonb#>>'{capture,manifest,raw,capture,data_source_id,value}' =
                    data_source_id AND
                receipt::jsonb#>>'{capture,references,event,event_id,value}' = event_id AND
                receipt::jsonb#>>'{capture,native,fixture_id}' = native_fixture_id::text
            ) IS TRUE)
        )
    """)
    op.execute(
        "CREATE INDEX ix_sportmonks_capture_event ON sportmonks_capture_receipts "
        "(event_id, capture_id)"
    )
    op.execute("""
        CREATE FUNCTION edgeeagle_sportmonks_receipt_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
            RAISE EXCEPTION 'Sportmonks capture receipts are immutable' USING ERRCODE = '23514';
        END $$
    """)
    op.execute("""
        CREATE TRIGGER sportmonks_capture_receipts_immutable
        BEFORE UPDATE OR DELETE OR TRUNCATE ON sportmonks_capture_receipts
        FOR EACH STATEMENT EXECUTE FUNCTION edgeeagle_sportmonks_receipt_immutable()
    """)


def downgrade() -> None:
    op.execute("LOCK TABLE sportmonks_capture_receipts IN ACCESS EXCLUSIVE MODE")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM sportmonks_capture_receipts) THEN
                RAISE EXCEPTION 'Cannot downgrade with retained Sportmonks receipts';
            END IF;
        END $$;
    """)
    op.drop_table("sportmonks_capture_receipts")
    op.execute("DROP FUNCTION edgeeagle_sportmonks_receipt_immutable()")
