"""Establish a migration baseline without premature domain tables."""

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Alembic records this revision; Phase 2 will add canonical domain tables."""


def downgrade() -> None:
    """The baseline owns no tables to remove."""
