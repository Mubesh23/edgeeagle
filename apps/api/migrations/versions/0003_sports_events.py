"""Persist the sport-neutral event hierarchy with relational consistency guards."""

import sqlalchemy as sa
from alembic import op

revision = "0003_sports_events"
down_revision = "0002_source_venue"
branch_labels = None
depends_on = None


def _id(name: str, *, primary: bool = False) -> sa.Column[str]:
    return sa.Column(name, sa.Text(collation="C"), primary_key=primary, nullable=False)


def _text(name: str, *, nullable: bool = False) -> sa.Column[str]:
    return sa.Column(name, sa.Text(), nullable=nullable)


def _checks(table: str, *columns: str) -> list[sa.CheckConstraint]:
    # Keep applied migrations self-contained; do not import evolving domain rules.
    return [
        sa.CheckConstraint(
            f"{column} <> '' AND {column} !~ '^[[:space:]]|[[:space:]]$'",
            name=f"ck_{table}_{column}_text",
        )
        for column in columns
    ]


def _fk(table: str, columns: list[str], parent: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        columns,
        [f"{parent}.{column}" for column in columns],
        name=f"fk_{table}_{parent}",
        ondelete="RESTRICT",
        onupdate="RESTRICT",
    )


def upgrade() -> None:
    op.create_table(
        "sports",
        _id("sport_id", primary=True),
        _text("code"),
        _text("name"),
        *_checks("sports", "sport_id", "code", "name"),
    )
    op.create_table(
        "competitions",
        _id("competition_id", primary=True),
        _id("sport_id"),
        _text("name"),
        _text("country_or_region"),
        _text("gender_or_division", nullable=True),
        *_checks(
            "competitions", "competition_id", "name", "country_or_region", "gender_or_division"
        ),
        _fk("competitions", ["sport_id"], "sports"),
        sa.UniqueConstraint("competition_id", "sport_id", name="uq_competitions_id_sport"),
    )
    op.create_table(
        "seasons",
        _id("season_id", primary=True),
        _id("competition_id"),
        _text("name"),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        *_checks("seasons", "season_id", "name"),
        _fk("seasons", ["competition_id"], "competitions"),
        sa.UniqueConstraint("season_id", "competition_id", name="uq_seasons_id_competition"),
        sa.CheckConstraint(
            "isfinite(starts_at) AND isfinite(ends_at) AND ends_at >= starts_at",
            name="ck_seasons_time_range",
        ),
    )
    op.create_table(
        "participants",
        _id("participant_id", primary=True),
        _id("sport_id"),
        _text("participant_type"),
        _text("canonical_name"),
        *_checks("participants", "participant_id", "participant_type", "canonical_name"),
        _fk("participants", ["sport_id"], "sports"),
        sa.UniqueConstraint("participant_id", "sport_id", name="uq_participants_id_sport"),
    )
    op.create_table(
        "events",
        _id("event_id", primary=True),
        _id("sport_id"),
        _id("competition_id"),
        _id("season_id"),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        _text("status"),
        _text("venue_location", nullable=True),
        *_checks("events", "event_id", "status", "venue_location"),
        _fk("events", ["competition_id", "sport_id"], "competitions"),
        _fk("events", ["season_id", "competition_id"], "seasons"),
        sa.UniqueConstraint("event_id", "sport_id", name="uq_events_id_sport"),
        sa.CheckConstraint("isfinite(starts_at)", name="ck_events_starts_at_finite"),
    )
    op.create_table(
        "event_participants",
        _id("event_id", primary=True),
        _id("participant_id", primary=True),
        _id("sport_id"),
        _text("role"),
        *_checks("event_participants", "role"),
        _fk("event_participants", ["event_id", "sport_id"], "events"),
        _fk("event_participants", ["participant_id", "sport_id"], "participants"),
    )

    # PostgreSQL does not automatically index the referencing side of a FK.
    for table, columns in (
        ("competitions", ["sport_id"]),
        ("seasons", ["competition_id"]),
        ("participants", ["sport_id"]),
        ("events", ["competition_id", "sport_id"]),
        ("events", ["season_id", "competition_id"]),
        ("event_participants", ["event_id", "sport_id"]),
        ("event_participants", ["participant_id", "sport_id"]),
    ):
        op.create_index(f"ix_{table}_{'_'.join(columns)}", table, columns)


def downgrade() -> None:
    for table in (
        "event_participants",
        "events",
        "participants",
        "seasons",
        "competitions",
        "sports",
    ):
        op.drop_table(table)
