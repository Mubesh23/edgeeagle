from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.exc import DBAPIError

from edgeeagle_persistence.provenance import PostgresDataSourceRepository
from tests.integration.test_repositories import repository_engine as repository_engine
from tests.unit.test_odds_receipts import receipt


def test_odds_schema_guards_and_downgrade(repository_engine: Engine) -> None:
    capture, body, _ = receipt()
    with repository_engine.begin() as conn:
        PostgresDataSourceRepository(conn).add(capture.evidence[0].references.source)
        conn.execute(
            text("INSERT INTO odds_capture_receipts VALUES (:id, :source, :body)"),
            {
                "id": "a" * 64,
                "source": capture.manifest.raw.capture.data_source_id.value,
                "body": body.decode(),
            },
        )
        for sql in (
            "UPDATE odds_capture_receipts SET snapshot = snapshot",
            "DELETE FROM odds_capture_receipts",
            "TRUNCATE odds_capture_receipts",
        ):
            with pytest.raises(DBAPIError), conn.begin_nested():
                conn.execute(text(sql))
        config = Config(str(Path("apps/api/alembic.ini").resolve()))
        config.attributes["connection"] = conn
        with pytest.raises(DBAPIError, match="Cannot downgrade"), conn.begin_nested():
            command.downgrade(config, "0011_market_quotes")
        assert conn.scalar(text("SELECT count(*) FROM odds_capture_receipts")) == 1
        with pytest.raises(DBAPIError), conn.begin_nested():
            conn.execute(
                text("INSERT INTO odds_capture_receipts VALUES (:id, :source, '{}')"),
                {"id": "b" * 64, "source": capture.manifest.raw.capture.data_source_id.value},
            )


def test_empty_odds_schema_can_downgrade_and_upgrade(repository_engine: Engine) -> None:
    with repository_engine.begin() as conn:
        config = Config(str(Path("apps/api/alembic.ini").resolve()))
        config.attributes["connection"] = conn
        command.downgrade(config, "0011_market_quotes")
        assert conn.scalar(text("SELECT to_regclass('odds_capture_receipts')")) is None
        command.upgrade(config, "head")
        assert conn.scalar(text("SELECT count(*) FROM odds_capture_quotes")) == 0
