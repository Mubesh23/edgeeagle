"""Permit additive mapped receipts without rewriting immutable legacy snapshots."""

from alembic import op

revision = "0009_mapped_receipts"
down_revision = "0008_event_consumption"
branch_labels = None
depends_on = None

_IDENTITY = (
    "jsonb_typeof(snapshot->'candidate') = 'object' AND "
    "snapshot#>>'{candidate,event,event_id,value}' = event_id AND "
    "snapshot#>>'{candidate,raw,capture,data_source_id,value}' = data_source_id AND "
    "snapshot#>>'{candidate,provider_key,data_source_id,value}' = data_source_id"
)


def upgrade() -> None:
    op.drop_constraint("ck_normalization_snapshot_identity", "event_normalizations", type_="check")
    op.create_check_constraint(
        "ck_normalization_snapshot_identity",
        "event_normalizations",
        "((snapshot->'format' = '1'::jsonb OR "
        "(snapshot->'format' = '2'::jsonb AND "
        "jsonb_typeof(snapshot#>'{candidate,mapping_evidence}') = 'object')) AND "
        + _IDENTITY
        + ") IS TRUE",
    )


def downgrade() -> None:
    # Prevent concurrent format-2 insertion between the guard and constraint replacement.
    op.execute("LOCK TABLE event_normalizations IN ACCESS EXCLUSIVE MODE")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM event_normalizations WHERE snapshot->'format' = '2'::jsonb)
            THEN RAISE EXCEPTION 'Cannot downgrade while format-2 receipts exist'
                USING ERRCODE = '23514';
            END IF;
        END $$
    """)
    op.drop_constraint("ck_normalization_snapshot_identity", "event_normalizations", type_="check")
    op.create_check_constraint(
        "ck_normalization_snapshot_identity",
        "event_normalizations",
        "(snapshot->'format' = '1'::jsonb AND " + _IDENTITY + ") IS TRUE",
    )
