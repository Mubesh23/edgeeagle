"""Exercise migrations in an isolated database, never resetting application data."""

import os
from pathlib import Path
from uuid import uuid4

import psycopg
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy import URL, create_engine, text


def test_migration_upgrade_repeat_downgrade_and_reapply() -> None:
    port = int(os.environ.get("EDGEEAGLE_POSTGRES_PORT", "55432"))
    database = f"edgeeagle_migration_test_{uuid4().hex}"
    with psycopg.connect(
        host="127.0.0.1",
        port=port,
        user="edgeeagle",
        password="edgeeagle-local",
        dbname="postgres",
        connect_timeout=5,
        autocommit=True,
    ) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        engine = create_engine(
            URL.create(
                "postgresql+psycopg",
                username="edgeeagle",
                password="edgeeagle-local",
                host="127.0.0.1",
                port=port,
                database=database,
            ),
            connect_args={"connect_timeout": 5},
        )
        try:
            config = Config(str(Path(__file__).resolve().parents[2] / "apps/api/alembic.ini"))
            with engine.begin() as connection:
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
                command.upgrade(config, "head")
                assert connection.scalars(
                    text("SELECT version_num FROM alembic_version")
                ).all() == ["0001_foundation"]
            # A separate transaction must observe the committed migration state.
            with engine.begin() as connection:
                config.attributes["connection"] = connection
                assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                    "0001_foundation"
                )
                command.downgrade(config, "base")
                assert connection.scalar(text("SELECT count(*) FROM alembic_version")) == 0
                command.upgrade(config, "head")
                assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                    "0001_foundation"
                )
        finally:
            engine.dispose()
            admin.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database)))
