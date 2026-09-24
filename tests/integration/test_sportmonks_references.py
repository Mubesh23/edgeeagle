"""Pinned Sportmonks mapping reads and authored Floci-to-candidate composition."""

from dataclasses import replace
from unittest.mock import Mock

import pytest
from mypy_boto3_s3 import S3Client
from sqlalchemy import Connection, Engine, text
from sqlalchemy.exc import InternalError

from edgeeagle_domain.mappings import MappingStatus
from edgeeagle_domain.raw import RawPayloadIntegrityError
from edgeeagle_domain.sports import EventId
from edgeeagle_ingestion.offline import LocalFileImporter
from edgeeagle_ingestion.service import ingest_raw
from edgeeagle_ingestion.sportmonks_normalization import normalize_sportmonks_capture
from edgeeagle_ingestion.sportmonks_references import (
    ResolvedSportmonksReferences,
    resolve_sportmonks_references,
)
from edgeeagle_persistence.mappings import PostgresMappingRepository
from edgeeagle_persistence.provenance import PostgresDataSourceRepository
from edgeeagle_persistence.raw import S3RawPayloadStore
from edgeeagle_persistence.sportmonks_references import (
    PostgresSportmonksReferenceResolver,
    sportmonks_reference_reads,
)
from edgeeagle_persistence.sports import PostgresSportsRepository
from tests.integration.test_raw_storage import raw_bucket as raw_bucket
from tests.integration.test_repositories import repository_engine as repository_engine
from tests.unit.test_sportmonks_manifest import FIXTURE, NOW, manifest
from tests.unit.test_sportmonks_references import setup_references


def seed(conn: Connection, refs: ResolvedSportmonksReferences) -> None:
    c = refs.context
    PostgresDataSourceRepository(conn).add(refs.source)
    sports = PostgresSportsRepository(conn)
    sports.add_sport(c.sport)
    sports.add_competition(c.competition)
    sports.add_season(c.season)
    sports.add_participant(c.home)
    sports.add_participant(c.away)
    sports.add_event(refs.event, refs.entries)
    for row in refs.revisions:
        PostgresMappingRepository(conn).append(row)


@pytest.mark.parametrize("change", ["revoked", "corrected"])
def test_sportmonks_pinned_snapshot_survives_committed_mapping_changes(
    repository_engine: Engine,
    change: str,
) -> None:
    args = setup_references()
    expected = resolve_sportmonks_references(*args, as_of=NOW)
    with repository_engine.begin() as conn:
        seed(conn, expected)
    reads = sportmonks_reference_reads(repository_engine)
    corrected_event = replace(expected.event, event_id=EventId("corrected-event"))
    with reads() as reader:
        assert reader.resolve(args[0], as_of=NOW) == expected
        with repository_engine.begin() as writer:
            revision = replace(expected.event_revision, revision=2)
            if change == "revoked":
                revision = replace(revision, status=MappingStatus.REVOKED)
            else:
                PostgresSportsRepository(writer).add_event(
                    corrected_event,
                    tuple(replace(e, event_id=corrected_event.event_id) for e in expected.entries),
                )
                revision = replace(revision, canonical_entity_id=corrected_event.event_id)
            PostgresMappingRepository(writer).append(revision)
            writer.execute(
                text("UPDATE participants SET canonical_name = 'Changed after snapshot'")
            )
        assert reader.resolve(args[0], as_of=NOW) == expected
    with reads() as reader:
        if change == "revoked":
            with pytest.raises(ValueError, match="revoked"):
                reader.resolve(args[0], as_of=NOW)
        else:
            fresh = reader.resolve(args[0], as_of=NOW)
            assert fresh.event == corrected_event
            assert fresh.event_revision == revision
            assert fresh.context.home.canonical_name == "Changed after snapshot"
    assert expected.event_revision.revision == 1
    assert expected.context.home.canonical_name != "Changed after snapshot"


def test_sportmonks_transaction_guards_and_cleanup(repository_engine: Engine) -> None:
    keys = setup_references()[0]
    with repository_engine.connect() as conn:
        with pytest.raises(RuntimeError, match="active"):
            PostgresSportmonksReferenceResolver(conn).resolve(keys, as_of=NOW)
        with conn.begin():
            with pytest.raises(RuntimeError, match="REPEATABLE READ"):
                PostgresSportmonksReferenceResolver(conn).resolve(keys, as_of=NOW)
    with repository_engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        with conn.begin(), pytest.raises(RuntimeError, match="Autocommit"):
            PostgresSportmonksReferenceResolver(conn).resolve(keys, as_of=NOW)
    with repository_engine.connect().execution_options(isolation_level="REPEATABLE READ") as conn:
        with conn.begin(), pytest.raises(RuntimeError, match="read-only"):
            PostgresSportmonksReferenceResolver(conn).resolve(keys, as_of=NOW)
    with pytest.raises(ValueError, match="source"):
        with sportmonks_reference_reads(repository_engine)() as reader:
            conn = reader._connection  # type: ignore[attr-defined]
            assert conn.scalar(text("SHOW transaction_read_only")) == "on"
            assert conn.scalar(text("SHOW statement_timeout")) == "5s"
            assert conn.scalar(text("SHOW idle_in_transaction_session_timeout")) == "5s"
            reader.resolve(keys, as_of=NOW)
    assert conn.closed
    with sportmonks_reference_reads(repository_engine)() as reader:
        conn = reader._connection  # type: ignore[attr-defined]
        with pytest.raises(InternalError), conn.begin_nested():
            conn.execute(text("UPDATE events SET status = 'SCHEDULED'"))
    assert conn.closed


def test_sportmonks_retained_raw_to_canonical_candidate(
    repository_engine: Engine,
    raw_bucket: tuple[S3Client, str],
) -> None:
    expected = resolve_sportmonks_references(*setup_references(), as_of=NOW)
    with repository_engine.begin() as conn:
        seed(conn, expected)
    client, bucket = raw_bucket
    store = S3RawPayloadStore(client, bucket)
    m = manifest()
    assert (
        ingest_raw(LocalFileImporter(FIXTURE, m.raw.capture, max_bytes=1024 * 1024), store) == m.raw
    )
    reads = sportmonks_reference_reads(repository_engine)
    result = normalize_sportmonks_capture(store, m, reads, as_of=NOW)
    assert result.references == expected
    assert normalize_sportmonks_capture(store, m, reads, as_of=NOW) == result
    assert result.manifest.usage == "SYNTHETIC_ONLY"
    assert result.manifest.raw.capture.available_at is None
    with repository_engine.begin() as conn:
        assert conn.scalar(text("SELECT count(*) FROM events")) == 1
        assert conn.scalar(text("SELECT count(*) FROM provider_mapping_revisions")) == 6
        assert conn.scalar(text("SELECT count(*) FROM event_normalizations")) == 0
        assert conn.scalar(text("SELECT count(*) FROM event_outbox")) == 0
        assert PostgresSportsRepository(conn).get_event(expected.event.event_id) == expected.event
    # Corrupt only the disposable test bucket; reject before any reference context.
    key = client.list_objects_v2(Bucket=bucket)["Contents"][0]["Key"]
    client.put_object(Bucket=bucket, Key=key, Body=b"corrupt")
    forbidden_reads = Mock()
    with pytest.raises(RawPayloadIntegrityError):
        normalize_sportmonks_capture(store, m, forbidden_reads, as_of=NOW)
    forbidden_reads.assert_not_called()
