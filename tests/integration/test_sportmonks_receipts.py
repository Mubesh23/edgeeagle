"""Sportmonks receipt schema and verified reader against disposable PostgreSQL."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import DBAPIError

from edgeeagle_ingestion.sportmonks_receipts import (
    encode_sportmonks_receipt,
    sportmonks_capture_identity,
)
from edgeeagle_persistence.sportmonks_receipts import (
    PostgresSportmonksReceiptReader,
    SportmonksReceiptIntegrityError,
)
from tests.integration.test_repositories import repository_engine as repository_engine
from tests.integration.test_sportmonks_references import seed
from tests.unit.test_sportmonks_receipts import capture


def migration_config(connection: Connection) -> Config:
    config = Config(str(Path("apps/api/alembic.ini").resolve()))
    config.attributes["connection"] = connection
    return config


def test_sportmonks_schema_reader_integrity_and_downgrade_guard(
    repository_engine: Engine,
) -> None:
    candidate, _ = capture()
    identity = sportmonks_capture_identity(candidate)
    body = encode_sportmonks_receipt(candidate)
    refs = candidate.references
    with repository_engine.begin() as connection:
        seed(connection, refs)
        connection.execute(
            text("""INSERT INTO sportmonks_capture_receipts
                VALUES (:id, :source, :event, :fixture, 1, :body)"""),
            {
                "id": identity,
                "source": refs.source.data_source_id.value,
                "event": refs.event.event_id.value,
                "fixture": candidate.native.fixture_id,
                "body": body.decode("ascii"),
            },
        )
        reader = PostgresSportmonksReceiptReader(connection)
        assert reader.get(identity) == candidate
        assert reader.get("0" * 64) is None
        for sql in (
            "UPDATE sportmonks_capture_receipts SET receipt = receipt",
            "DELETE FROM sportmonks_capture_receipts",
            "TRUNCATE sportmonks_capture_receipts",
        ):
            with pytest.raises(DBAPIError), connection.begin_nested():
                connection.execute(text(sql))
        with pytest.raises(DBAPIError, match="Cannot downgrade"), connection.begin_nested():
            command.downgrade(migration_config(connection), "0012_odds_captures")
        assert connection.scalar(text("SELECT count(*) FROM sportmonks_capture_receipts")) == 1
        # Simulate privileged corruption after temporarily removing the SQL shape guard.
        savepoint = connection.begin_nested()
        try:
            connection.execute(
                text("""ALTER TABLE sportmonks_capture_receipts
                    DISABLE TRIGGER sportmonks_capture_receipts_immutable""")
            )
            connection.execute(
                text("""ALTER TABLE sportmonks_capture_receipts
                    DROP CONSTRAINT ck_sportmonks_receipt_identity""")
            )
            connection.execute(
                text(
                    "UPDATE sportmonks_capture_receipts SET receipt = '{}' WHERE capture_id = :id"
                ),
                {"id": identity},
            )
            with pytest.raises(SportmonksReceiptIntegrityError):
                reader.get(identity)
        finally:
            savepoint.rollback()


def test_empty_sportmonks_schema_downgrades_and_reapplies(repository_engine: Engine) -> None:
    with repository_engine.begin() as connection:
        config = migration_config(connection)
        command.downgrade(config, "0012_odds_captures")
        assert connection.scalar(text("SELECT to_regclass('sportmonks_capture_receipts')")) is None
        command.upgrade(config, "head")
        assert connection.scalar(text("SELECT count(*) FROM sportmonks_capture_receipts")) == 0
