"""Append-only typed provider mapping storage; repository workflow follows separately."""

import sqlalchemy as sa
from alembic import op

revision = "0004_mapping_history"
down_revision = "0003_sports_events"
branch_labels = None
depends_on = None

KEY = ("data_source_id", "provider_entity_type", "provider_entity_id")
TARGETS = (
    ("SPORT", "sport_id", "sports"),
    ("COMPETITION", "competition_id", "competitions"),
    ("SEASON", "season_id", "seasons"),
    ("PARTICIPANT", "participant_id", "participants"),
    ("EVENT", "event_id", "events"),
    ("VENUE", "venue_id", "venues"),
)


def _text(name: str, *, nullable: bool = False) -> sa.Column[str]:
    return sa.Column(name, sa.Text(collation="C"), nullable=nullable)


def _nonblank(name: str, prefix: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(
        f"{name} <> '' AND {name} !~ '^[[:space:]]|[[:space:]]$'",
        name=f"ck_{prefix}_{name}_text",
    )


def upgrade() -> None:
    op.create_table(
        "provider_mapping_keys",
        *(_text(name) for name in KEY),
        _text("target_kind"),
        sa.PrimaryKeyConstraint(*KEY, name="pk_provider_mapping_keys"),
        sa.UniqueConstraint(*KEY, "target_kind", name="uq_mapping_key_kind"),
        *(_nonblank(name, "mapping_key") for name in KEY),
        sa.CheckConstraint(
            "target_kind IN ('SPORT', 'COMPETITION', 'SEASON', 'PARTICIPANT', 'EVENT', 'VENUE')",
            name="ck_mapping_key_kind",
        ),
        sa.ForeignKeyConstraint(
            ["data_source_id"],
            ["data_sources.data_source_id"],
            name="fk_mapping_key_source",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
    )
    op.create_table(
        "provider_mapping_revisions",
        *(_text(name) for name in KEY),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column(
            "previous_revision",
            sa.BigInteger(),
            sa.Computed("NULLIF(revision - 1, 0)", persisted=True),
        ),
        _text("target_kind"),
        *(_text(column, nullable=True) for _, column, _ in TARGETS),
        _text("mapping_method"),
        sa.Column("confidence", sa.Numeric(), nullable=True),
        _text("validated_by"),
        *(
            sa.Column(name, sa.DateTime(timezone=True), nullable=False)
            for name in ("validated_at", "available_at", "ingested_at")
        ),
        _text("status"),
        sa.PrimaryKeyConstraint(*KEY, "revision", name="pk_provider_mapping_revisions"),
        sa.ForeignKeyConstraint(
            [*KEY, "target_kind"],
            [f"provider_mapping_keys.{name}" for name in (*KEY, "target_kind")],
            name="fk_mapping_revision_key",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            [*KEY, "previous_revision"],
            [f"provider_mapping_revisions.{name}" for name in (*KEY, "revision")],
            name="fk_mapping_revision_previous",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        *(
            sa.ForeignKeyConstraint(
                [column],
                [f"{table}.{column}"],
                name=f"fk_mapping_revision_{column}",
                ondelete="RESTRICT",
                onupdate="RESTRICT",
            )
            for _, column, table in TARGETS
        ),
        sa.CheckConstraint("revision > 0", name="ck_mapping_revision_positive"),
        sa.CheckConstraint("status IN ('MAPPED', 'REVOKED')", name="ck_mapping_revision_status"),
        sa.CheckConstraint("revision <> 1 OR status = 'MAPPED'", name="ck_mapping_first_mapped"),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_mapping_confidence"),
        sa.CheckConstraint(
            "isfinite(validated_at) AND isfinite(available_at) AND isfinite(ingested_at) "
            "AND validated_at <= available_at AND available_at <= ingested_at",
            name="ck_mapping_decision_times",
        ),
        _nonblank("mapping_method", "mapping_revision"),
        _nonblank("validated_by", "mapping_revision"),
        sa.CheckConstraint(
            "num_nonnulls(" + ", ".join(column for _, column, _ in TARGETS) + ") = 1",
            name="ck_mapping_one_target",
        ),
        sa.CheckConstraint(
            " OR ".join(
                f"(target_kind = '{kind}' AND {column} IS NOT NULL)" for kind, column, _ in TARGETS
            ),
            name="ck_mapping_target_kind",
        ),
    )
    # Existing PK prefixes cover source/key lookups; explicit indexes cover other FKs.
    op.create_index(
        "ix_mapping_revision_previous", "provider_mapping_revisions", [*KEY, "previous_revision"]
    )
    for _, column, _ in TARGETS:
        op.create_index(f"ix_mapping_revision_{column}", "provider_mapping_revisions", [column])
    op.execute("""
        CREATE FUNCTION edgeeagle_mapping_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'Provider mapping history is append-only'
                USING ERRCODE = '23514';
        END;
        $$
    """)
    for table in ("provider_mapping_keys", "provider_mapping_revisions"):
        op.execute(f"""
            CREATE TRIGGER {table}_immutable
            BEFORE UPDATE OR DELETE OR TRUNCATE ON {table}
            FOR EACH STATEMENT EXECUTE FUNCTION edgeeagle_mapping_immutable()
        """)


def downgrade() -> None:
    op.drop_table("provider_mapping_revisions")
    op.drop_table("provider_mapping_keys")
    op.execute("DROP FUNCTION edgeeagle_mapping_immutable()")
