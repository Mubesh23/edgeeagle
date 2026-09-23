"""Permit additive full-time soccer score receipts without rewriting old data."""

from alembic import op

revision = "0010_soccer_receipts"
down_revision = "0009_mapped_receipts"
branch_labels = None
depends_on = None

_IDENTITY = (
    "jsonb_typeof(snapshot->'candidate') = 'object' AND "
    "snapshot#>>'{candidate,event,event_id,value}' = event_id AND "
    "snapshot#>>'{candidate,raw,capture,data_source_id,value}' = data_source_id AND "
    "snapshot#>>'{candidate,provider_key,data_source_id,value}' = data_source_id"
)
_LEGACY = (
    "snapshot->'format' = '1'::jsonb OR "
    "(snapshot->'format' = '2'::jsonb AND "
    "jsonb_typeof(snapshot#>'{candidate,mapping_evidence}') = 'object')"
)


def upgrade() -> None:
    op.drop_constraint("ck_normalization_snapshot_identity", "event_normalizations", type_="check")
    op.create_check_constraint(
        "ck_normalization_snapshot_identity",
        "event_normalizations",
        "((" + _LEGACY + " OR (snapshot->'format' = '3'::jsonb AND "
        "jsonb_typeof(snapshot#>'{candidate,mapping_evidence}') = 'object' AND "
        "jsonb_typeof(snapshot#>'{candidate,soccer_result}') = 'object')) AND "
        + _IDENTITY
        + ") IS TRUE",
    )


def downgrade() -> None:
    op.execute("LOCK TABLE event_normalizations IN ACCESS EXCLUSIVE MODE")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (SELECT 1 FROM event_normalizations WHERE snapshot->'format' = '3'::jsonb)
            THEN RAISE EXCEPTION 'Cannot downgrade while format-3 receipts exist'
                USING ERRCODE = '23514';
            END IF;
        END $$
    """)
    op.drop_constraint("ck_normalization_snapshot_identity", "event_normalizations", type_="check")
    op.create_check_constraint(
        "ck_normalization_snapshot_identity",
        "event_normalizations",
        "((" + _LEGACY + ") AND " + _IDENTITY + ") IS TRUE",
    )
