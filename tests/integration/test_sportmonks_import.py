"""Complete authored Sportmonks local-file to immutable-receipt workflow."""

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest
from mypy_boto3_s3 import S3Client
from sqlalchemy import Engine, text

from edgeeagle_domain.mappings import MappingStatus
from edgeeagle_ingestion.offline import LocalFileImporter
from edgeeagle_ingestion.sportmonks_acceptance import SportmonksReceiptRepository
from edgeeagle_ingestion.sportmonks_import import (
    accept_retained_sportmonks_capture,
    import_sportmonks_capture,
)
from edgeeagle_ingestion.sportmonks_normalization import NormalizedSportmonksFixture
from edgeeagle_ingestion.sportmonks_receipts import replay_sportmonks_receipt
from edgeeagle_ingestion.sportmonks_references import (
    SportmonksReferenceResolver,
    resolve_sportmonks_references,
)
from edgeeagle_persistence.mappings import PostgresMappingRepository
from edgeeagle_persistence.raw import S3RawPayloadStore
from edgeeagle_persistence.sportmonks_receipts import (
    PostgresSportmonksReceiptRepository,
    sportmonks_receipt_transactions,
)
from edgeeagle_persistence.sportmonks_references import sportmonks_reference_reads
from tests.integration.test_raw_storage import raw_bucket as raw_bucket
from tests.integration.test_repositories import repository_engine as repository_engine
from tests.integration.test_sportmonks_references import seed
from tests.unit.test_sportmonks_manifest import FIXTURE, NOW, manifest
from tests.unit.test_sportmonks_references import setup_references


def test_authored_file_to_floci_and_atomic_receipt_replay(
    repository_engine: Engine,
    raw_bucket: tuple[S3Client, str],
) -> None:
    references = setup_references()
    resolved = resolve_sportmonks_references(*references, as_of=NOW)
    with repository_engine.begin() as connection:
        seed(connection, resolved)

    client, bucket = raw_bucket
    store = S3RawPayloadStore(client, bucket)
    capture = manifest()
    importer = LocalFileImporter(FIXTURE, capture.raw.capture, max_bytes=1024 * 1024)
    reads = sportmonks_reference_reads(repository_engine)
    transactions = sportmonks_receipt_transactions(repository_engine)

    first = import_sportmonks_capture(importer, store, capture, reads, transactions, as_of=NOW)
    second = import_sportmonks_capture(importer, store, capture, reads, transactions, as_of=NOW)
    assert first.raw == second.raw == capture.raw
    assert first.capture_id == second.capture_id
    assert first.inserted_receipts == 1
    assert second.inserted_receipts == 0
    assert first.receipt == second.receipt
    assert first.receipt.references == resolved
    assert first.receipt.manifest.usage == "SYNTHETIC_ONLY"
    assert first.receipt.manifest.raw.capture.available_at is None

    # Later canonical display changes and mapping revocation do not rewrite or
    # prevent replay of the already retained observation evidence.
    with repository_engine.begin() as connection:
        connection.execute(
            text("UPDATE participants SET canonical_name = 'Changed after acceptance'")
        )
        revoked = replace(resolved.event_revision, revision=2, status=MappingStatus.REVOKED)
        PostgresMappingRepository(connection).append(revoked)

    retried = accept_retained_sportmonks_capture(store, first.receipt, transactions)
    assert retried.receipt == first.receipt
    assert retried.capture_id == first.capture_id
    assert retried.inserted_receipts == 0
    assert replay_sportmonks_receipt(store, first.receipt) == first.receipt
    with repository_engine.begin() as connection:
        assert connection.scalar(text("SELECT count(*) FROM sportmonks_capture_receipts")) == 1
        assert connection.scalar(text("SELECT count(*) FROM events")) == 1
        assert connection.scalar(text("SELECT count(*) FROM provider_mapping_revisions")) == 7
        assert connection.scalar(text("SELECT count(*) FROM event_outbox")) == 0


def test_changed_local_file_is_rejected_before_reference_or_write_transactions(
    raw_bucket: tuple[S3Client, str],
    tmp_path: Path,
) -> None:
    client, bucket = raw_bucket
    path = tmp_path / "changed.json"
    path.write_bytes(FIXTURE.read_bytes())
    capture = manifest()
    importer = LocalFileImporter(path, capture.raw.capture, max_bytes=1024 * 1024)
    path.write_bytes(FIXTURE.read_bytes() + b" ")

    def forbidden_reads() -> AbstractContextManager[SportmonksReferenceResolver]:
        raise AssertionError("must reject changed bytes before opening a transaction")

    def forbidden_transactions() -> AbstractContextManager[SportmonksReceiptRepository]:
        raise AssertionError("must reject changed bytes before opening a transaction")

    with pytest.raises(ValueError, match="manifest"):
        import_sportmonks_capture(
            importer,
            S3RawPayloadStore(client, bucket),
            capture,
            forbidden_reads,
            forbidden_transactions,
            as_of=NOW,
        )


def test_import_readback_mismatch_rolls_back_new_receipt(
    repository_engine: Engine,
    raw_bucket: tuple[S3Client, str],
) -> None:
    references = setup_references()
    resolved = resolve_sportmonks_references(*references, as_of=NOW)
    with repository_engine.begin() as connection:
        seed(connection, resolved)

    client, bucket = raw_bucket
    store = S3RawPayloadStore(client, bucket)
    capture = replace(manifest(), simulated_snapshot_at=NOW + timedelta(seconds=1))
    importer = LocalFileImporter(FIXTURE, capture.raw.capture, max_bytes=1024 * 1024)
    real_transactions = sportmonks_receipt_transactions(repository_engine)

    class MissingReadback:
        def __init__(self, repository: PostgresSportmonksReceiptRepository) -> None:
            self._repository = repository

        def accept(self, receipt: NormalizedSportmonksFixture) -> int:
            return self._repository.accept(receipt)

        def get(self, capture_id: str) -> NormalizedSportmonksFixture | None:
            return None

    @contextmanager
    def mismatched_transactions() -> Iterator[MissingReadback]:
        with real_transactions() as repository:
            yield MissingReadback(repository)

    with pytest.raises(ValueError, match="receipt differs"):
        import_sportmonks_capture(
            importer,
            store,
            capture,
            sportmonks_reference_reads(repository_engine),
            mismatched_transactions,
            as_of=NOW,
        )
    with repository_engine.begin() as connection:
        assert connection.scalar(text("SELECT count(*) FROM sportmonks_capture_receipts")) == 0
