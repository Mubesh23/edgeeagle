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
    assert ScriptDirectory.from_config(config).get_heads() == ["0004_mapping_history"]
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
