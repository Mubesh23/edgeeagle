"""The migration graph and SQL export must work without a database."""

from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from pytest import MonkeyPatch


def test_baseline_has_one_head_and_can_emit_offline_sql(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv(
        "EDGEEAGLE_DATABASE_URL",
        "postgresql+psycopg://edgeeagle:edgeeagle-local@127.0.0.1:55432/edgeeagle",
    )
    output = StringIO()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"), output_buffer=output)
    assert ScriptDirectory.from_config(config).get_heads() == ["0009_mapped_receipts"]
    command.upgrade(config, "head", sql=True)
    assert "CREATE TABLE alembic_version" in output.getvalue()
    assert "0001_foundation" in output.getvalue()
    for table in ("data_sources", "venues", "data_source_capabilities", "venue_capabilities"):
        assert f"CREATE TABLE {table}" in output.getvalue()
    assert "FOREIGN KEY" in output.getvalue()
    assert "DROP TABLE" not in output.getvalue()
    for table in (
        "sports",
        "competitions",
        "seasons",
        "participants",
        "events",
        "event_participants",
    ):
        assert f"CREATE TABLE {table}" in output.getvalue()
    assert "TIMESTAMP WITH TIME ZONE" in output.getvalue()
    assert "CREATE TABLE provider_mapping_keys" in output.getvalue()
    assert "CREATE TABLE event_normalizations" in output.getvalue()
    assert "CREATE TABLE event_outbox" in output.getvalue()
    assert "CREATE TABLE event_outbox_delivery" in output.getvalue()
    assert "CREATE TABLE event_acceptance_consumptions" in output.getvalue()
    assert "CREATE TABLE provider_mapping_revisions" in output.getvalue()
    assert "GENERATED ALWAYS AS" in output.getvalue()
    assert "BEFORE UPDATE OR DELETE OR TRUNCATE" in output.getvalue()
    output.truncate(0)
    output.seek(0)
    command.downgrade(config, "0002_source_venue:0001_foundation", sql=True)
    sql = output.getvalue()
    assert sql.index("DROP TABLE venue_capabilities") < sql.index("DROP TABLE venues")
    assert sql.index("DROP TABLE data_source_capabilities") < sql.index("DROP TABLE data_sources")
    output.truncate(0)
    output.seek(0)
    command.downgrade(config, "0003_sports_events:0002_source_venue", sql=True)
    sql = output.getvalue()
    assert sql.index("DROP TABLE event_participants") < sql.index("DROP TABLE events")
    assert "DROP TABLE data_sources" not in sql
    output.truncate(0)
    output.seek(0)
    command.downgrade(config, "0004_mapping_history:0003_sports_events", sql=True)
    sql = output.getvalue()
    assert sql.index("DROP TABLE provider_mapping_revisions") < sql.index(
        "DROP TABLE provider_mapping_keys"
    )
    assert "DROP FUNCTION edgeeagle_mapping_immutable()" in sql
    assert "DROP TABLE sports" not in sql
    output.truncate(0)
    output.seek(0)
    command.downgrade(config, "0005_event_acceptance:0004_mapping_history", sql=True)
    assert "DROP TABLE event_normalizations" in output.getvalue()
    assert "DROP TABLE events" not in output.getvalue()
    output.truncate(0)
    output.seek(0)
    command.downgrade(config, "0006_event_outbox:0005_event_acceptance", sql=True)
    assert "DROP TABLE event_outbox" in output.getvalue()
    assert "DROP TABLE event_normalizations" not in output.getvalue()
    output.truncate(0)
    output.seek(0)
    command.downgrade(config, "0007_outbox_delivery:0006_event_outbox", sql=True)
    assert "DROP TABLE event_outbox_delivery;" in output.getvalue()
    assert "DROP TABLE event_outbox;" not in output.getvalue()
    output.truncate(0)
    output.seek(0)
    command.downgrade(config, "0009_mapped_receipts:0008_event_consumption", sql=True)
    assert "LOCK TABLE event_normalizations IN ACCESS EXCLUSIVE MODE" in output.getvalue()
    assert "Cannot downgrade while format-2 receipts exist" in output.getvalue()
    assert "DROP TABLE" not in output.getvalue()
    output.truncate(0)
    output.seek(0)
    command.downgrade(config, "0008_event_consumption:0007_outbox_delivery", sql=True)
    assert "DROP TABLE event_acceptance_consumptions;" in output.getvalue()
    assert "DROP TABLE event_outbox;" not in output.getvalue()
