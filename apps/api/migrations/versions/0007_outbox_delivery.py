"""Mutable delivery coordination, separate from immutable outbox envelopes."""

import sqlalchemy as sa
from alembic import op

revision = "0007_outbox_delivery"
down_revision = "0006_event_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Prevent old writers inserting between backfill and trigger installation.
    op.execute("LOCK TABLE event_outbox IN SHARE ROW EXCLUSIVE MODE")
    op.create_table(
        "event_outbox_delivery",
        sa.Column("notification_id", sa.Text(collation="C"), primary_key=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["notification_id"],
            ["event_outbox.notification_id"],
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            name="fk_delivery_intent",
        ),
        sa.CheckConstraint("attempts >= 0", name="ck_delivery_attempts"),
        sa.CheckConstraint(
            "((status = 'PENDING' AND claimed_at IS NULL AND lease_expires_at IS NULL "
            "AND acknowledged_at IS NULL) OR "
            "(status IN ('LEASED', 'PUBLISHED') AND attempts > 0 "
            "AND claimed_at IS NOT NULL AND lease_expires_at > claimed_at "
            "AND ((status = 'LEASED' AND acknowledged_at IS NULL) OR "
            "(status = 'PUBLISHED' AND acknowledged_at >= claimed_at "
            "AND acknowledged_at < lease_expires_at)))) IS TRUE",
            name="ck_delivery_state",
        ),
    )
    op.create_index(
        "ix_delivery_pending",
        "event_outbox_delivery",
        ["ready_at", "notification_id"],
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_index(
        "ix_delivery_expired",
        "event_outbox_delivery",
        ["lease_expires_at", "notification_id"],
        postgresql_where=sa.text("status = 'LEASED'"),
    )
    op.execute("""
        INSERT INTO event_outbox_delivery (notification_id, ready_at)
        SELECT notification_id, GREATEST(clock_timestamp(), (envelope->>'occurred_at')::timestamptz)
        FROM event_outbox
    """)
    op.execute("""
        CREATE FUNCTION edgeeagle_initialize_delivery() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            INSERT INTO event_outbox_delivery (notification_id, ready_at)
            VALUES (NEW.notification_id,
                GREATEST(clock_timestamp(), (NEW.envelope->>'occurred_at')::timestamptz));
            RETURN NEW;
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER event_outbox_initialize_delivery AFTER INSERT ON event_outbox
        FOR EACH ROW EXECUTE FUNCTION edgeeagle_initialize_delivery()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER event_outbox_initialize_delivery ON event_outbox")
    op.execute("DROP FUNCTION edgeeagle_initialize_delivery()")
    op.drop_table("event_outbox_delivery")
