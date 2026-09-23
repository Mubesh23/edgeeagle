"""Immutable verification receipts for the first EventAccepted consumer."""

import sqlalchemy as sa
from alembic import op

revision = "0008_event_consumption"
down_revision = "0007_outbox_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_acceptance_consumptions",
        sa.Column("notification_id", sa.Text(collation="C"), primary_key=True),
        sa.Column(
            "verified_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("clock_timestamp()"),
        ),
        sa.ForeignKeyConstraint(
            ["notification_id"],
            ["event_outbox.notification_id"],
            name="fk_consumption_intent",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
    )
    op.execute("""
        CREATE FUNCTION edgeeagle_consumption_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Event consumption receipts are immutable' USING ERRCODE = '23514';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER event_consumption_immutable
        BEFORE UPDATE OR DELETE OR TRUNCATE ON event_acceptance_consumptions
        FOR EACH STATEMENT EXECUTE FUNCTION edgeeagle_consumption_immutable()
    """)


def downgrade() -> None:
    op.drop_table("event_acceptance_consumptions")
    op.execute("DROP FUNCTION edgeeagle_consumption_immutable()")
