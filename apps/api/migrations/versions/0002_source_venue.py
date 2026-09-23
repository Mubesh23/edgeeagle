"""Persist independent data sources and venues, without provider catalog seeds."""

import sqlalchemy as sa
from alembic import op

revision = "0002_source_venue"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def _text_check(table: str, column: str) -> sa.CheckConstraint:
    # PostgreSQL guards empty/padded text. Domain constructors remain authoritative
    # for Python's full Unicode whitespace rules; never trim or coerce at storage.
    return sa.CheckConstraint(
        f"{column} <> '' AND {column} !~ '^[[:space:]]|[[:space:]]$'",
        name=f"ck_{table}_{column}_text",
    )


def upgrade() -> None:
    op.create_table(
        "data_sources",
        sa.Column("data_source_id", sa.Text(collation="C"), primary_key=True),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("source_type", sa.Text(), nullable=False),
        _text_check("data_sources", "data_source_id"),
        _text_check("data_sources", "code"),
        sa.CheckConstraint(
            "source_type IN ('SPORTS_DATA', 'ODDS_AGGREGATOR', 'VENUE_API', 'OFFLINE_DATASET')",
            name="ck_data_sources_source_type",
        ),
    )
    op.create_table(
        "venues",
        sa.Column("venue_id", sa.Text(collation="C"), primary_key=True),
        sa.Column("operator", sa.Text(), nullable=False),
        sa.Column("product", sa.Text(), nullable=False),
        sa.Column("jurisdiction", sa.Text(), nullable=False),
        sa.Column("venue_type", sa.Text(), nullable=False),
        *(
            _text_check("venues", field)
            for field in ("venue_id", "operator", "product", "jurisdiction")
        ),
        sa.CheckConstraint(
            "venue_type IN ('SPORTSBOOK', 'PREDICTION_MARKET', 'EXCHANGE')",
            name="ck_venues_venue_type",
        ),
    )
    for table, parent, identifier in (
        ("data_source_capabilities", "data_sources", "data_source_id"),
        ("venue_capabilities", "venues", "venue_id"),
    ):
        op.create_table(
            table,
            sa.Column(identifier, sa.Text(collation="C"), primary_key=True),
            sa.Column("capability", sa.Text(collation="C"), primary_key=True),
            sa.ForeignKeyConstraint(
                [identifier],
                [f"{parent}.{identifier}"],
                name=f"fk_{table}_{identifier}",
                ondelete="RESTRICT",
                onupdate="RESTRICT",
            ),
            _text_check(table, "capability"),
        )


def downgrade() -> None:
    # Only explicit downgrades remove data. Normal validation uses disposable DBs.
    op.drop_table("venue_capabilities")
    op.drop_table("data_source_capabilities")
    op.drop_table("venues")
    op.drop_table("data_sources")
