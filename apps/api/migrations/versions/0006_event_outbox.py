"""Immutable initial event publication intents; no legacy backfill."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0006_event_outbox"
down_revision = "0005_event_acceptance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_outbox",
        sa.Column("notification_id", sa.Text(collation="C"), primary_key=True),
        sa.Column("canonical_event_id", sa.Text(collation="C"), nullable=False, unique=True),
        sa.Column("envelope", JSONB(), nullable=False),
        sa.ForeignKeyConstraint(
            ["canonical_event_id"],
            ["event_normalizations.event_id"],
            name="fk_outbox_normalization",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.CheckConstraint(
            "(jsonb_typeof(envelope) = 'object' AND "
            "envelope->>'event_id' = notification_id AND "
            "envelope->>'event_type' = 'EventAccepted' AND "
            "envelope->'version' = '1'::jsonb AND "
            "envelope->'published_at' = 'null'::jsonb AND "
            "envelope#>>'{payload,canonical_event_id}' = canonical_event_id AND "
            "envelope#>>'{payload,acceptance_key}' ~ '^[0-9a-f]{64}$') IS TRUE",
            name="ck_outbox_envelope",
        ),
    )
    op.execute("""
        CREATE FUNCTION edgeeagle_outbox_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Event outbox intents are immutable' USING ERRCODE = '23514';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER event_outbox_immutable
        BEFORE UPDATE OR DELETE OR TRUNCATE ON event_outbox
        FOR EACH STATEMENT EXECUTE FUNCTION edgeeagle_outbox_immutable()
    """)


def downgrade() -> None:
    op.drop_table("event_outbox")
    op.execute("DROP FUNCTION edgeeagle_outbox_immutable()")
