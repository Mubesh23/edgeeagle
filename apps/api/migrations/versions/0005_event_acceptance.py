"""Immutable initial event normalization receipts."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0005_event_acceptance"
down_revision = "0004_mapping_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "event_normalizations",
        sa.Column("event_id", sa.Text(collation="C"), primary_key=True),
        sa.Column("data_source_id", sa.Text(collation="C"), nullable=False),
        sa.Column("acceptance_key", sa.Text(collation="C"), nullable=False, unique=True),
        sa.Column("snapshot", JSONB(), nullable=False),
        sa.CheckConstraint(
            "acceptance_key ~ '^[0-9a-f]{64}$'", name="ck_normalization_acceptance_key"
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["events.event_id"],
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            name="fk_normalization_event",
        ),
        sa.ForeignKeyConstraint(
            ["data_source_id"],
            ["data_sources.data_source_id"],
            ondelete="RESTRICT",
            onupdate="RESTRICT",
            name="fk_normalization_source",
        ),
        sa.CheckConstraint(
            "(snapshot->'format' = '1'::jsonb AND "
            "jsonb_typeof(snapshot->'candidate') = 'object' AND "
            "snapshot#>>'{candidate,event,event_id,value}' = event_id AND "
            "snapshot#>>'{candidate,raw,capture,data_source_id,value}' = data_source_id AND "
            "snapshot#>>'{candidate,provider_key,data_source_id,value}' = data_source_id) IS TRUE",
            name="ck_normalization_snapshot_identity",
        ),
    )
    op.create_index("ix_event_normalizations_source", "event_normalizations", ["data_source_id"])
    op.execute("""
        CREATE FUNCTION edgeeagle_normalization_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Event normalization receipts are immutable' USING ERRCODE = '23514';
        END;
        $$
    """)
    op.execute("""
        CREATE TRIGGER event_normalizations_immutable
        BEFORE UPDATE OR DELETE OR TRUNCATE ON event_normalizations
        FOR EACH STATEMENT EXECUTE FUNCTION edgeeagle_normalization_immutable()
    """)


def downgrade() -> None:
    op.drop_table("event_normalizations")
    op.execute("DROP FUNCTION edgeeagle_normalization_immutable()")
