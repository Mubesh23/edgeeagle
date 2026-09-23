"""Local CSV import composition; no cross-service transaction or hidden repair."""

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime

from edgeeagle_domain.raw import RawPayloadStore
from edgeeagle_ingestion.events import EventAcceptanceRepository
from edgeeagle_ingestion.fixture_references import FixtureReferenceReads
from edgeeagle_ingestion.football_data import FootballDataRequest, normalize_results
from edgeeagle_ingestion.manifest_storage import ManifestIntegrityError, ReplayManifestStore
from edgeeagle_ingestion.manifests import (
    EventReceiptCodec,
    ManifestCapture,
    ReplayDatasetManifest,
    encode_manifest,
)
from edgeeagle_ingestion.service import OfflineDatasetImporter, ingest_raw

AcceptanceTransactions = Callable[[], AbstractContextManager[EventAcceptanceRepository]]


def import_results_dataset(
    importer: OfflineDatasetImporter,
    raw_store: RawPayloadStore,
    requests: tuple[FootballDataRequest, ...],
    reads: FixtureReferenceReads,
    transactions: AcceptanceTransactions,
    manifests: ReplayManifestStore,
    codec: EventReceiptCodec,
    *,
    as_of: datetime,
) -> str:
    """Retain, normalize, atomically accept, then store an accepted-receipt snapshot.

    The caller's transaction context must commit on clean exit and roll back on
    errors. It must encompass the complete batch, not commit each repository call.
    Raw/manifest storage runs outside it. Original capture/context must be reused
    on retry. Manifest failure after commit leaves receipts retained, not undone.
    Returns the acknowledged replay-only dataset version; never publishes events.
    """
    reference = ingest_raw(importer, raw_store)
    candidates = normalize_results(raw_store, reference, requests, reads, as_of=as_of)
    retained = []
    with transactions() as repository:
        # Stable lock ordering prevents opposing batch order from inducing deadlocks.
        for candidate in sorted(candidates, key=lambda c: c.event.event_id.value):
            repository.accept(candidate)
            accepted = repository.get(candidate.event.event_id)
            if accepted is None or codec.encode(accepted) != codec.encode(candidate):
                raise ValueError("accepted receipt does not match normalized candidate")
            retained.append(accepted)
        # Validate metadata/size before committing canonical effects; S3 write follows commit.
        body = encode_manifest(
            ReplayDatasetManifest(
                captures=(ManifestCapture(raw=reference, candidates=tuple(retained)),)
            ),
            codec,
        )
    version = manifests.put(body)
    if version != json.loads(body)["dataset_version"]:
        raise ManifestIntegrityError("manifest storage returned a different dataset version")
    return version
