"""Whole-capture acceptance followed by immutable page/root publication (ADR-029)."""

from datetime import datetime

from edgeeagle_domain.raw import RawPayloadStore
from edgeeagle_ingestion.fixture_references import FixtureReferenceReads
from edgeeagle_ingestion.football_data import FootballDataRequest, normalize_season_results
from edgeeagle_ingestion.football_data_import import AcceptanceTransactions
from edgeeagle_ingestion.manifests import EventReceiptCodec
from edgeeagle_ingestion.season_bundle import (
    SeasonObjectIntegrityError,
    SeasonObjectStore,
    build_bundle,
    content_hash,
)
from edgeeagle_ingestion.service import OfflineDatasetImporter, ingest_raw


def import_season_dataset(
    importer: OfflineDatasetImporter,
    raw_store: RawPayloadStore,
    requests: tuple[FootballDataRequest, ...],
    reads: FixtureReferenceReads,
    transactions: AcceptanceTransactions,
    objects: SeasonObjectStore,
    codec: EventReceiptCodec,
    *,
    as_of: datetime,
) -> str:
    """Return the replay-only root hash only after every object is acknowledged.

    The caller's transaction context commits once on clean exit and rolls back
    the whole batch on error. Raw retention precedes it; page/root writes follow
    it. Storage failure cannot undo accepted receipts. Exact retries require the
    original capture, requests and unchanged reference context. No publication
    notifications, current-state repair or historical eligibility are implied.
    """
    reference = ingest_raw(importer, raw_store)
    candidates = normalize_season_results(raw_store, reference, requests, reads, as_of=as_of)
    retained = []
    with transactions() as repository:
        for candidate in sorted(candidates, key=lambda c: c.event.event_id.value):
            repository.accept(candidate)
            accepted = repository.get(candidate.event.event_id)
            if accepted is None or codec.encode(accepted) != codec.encode(candidate):
                raise ValueError("accepted receipt does not match normalized candidate")
            retained.append(accepted)
        # Fail any page/root encoding or size check before committing canonical effects.
        root, pages = build_bundle(reference, tuple(retained), codec)
    for body in (*pages, root):
        if objects.put(body) != content_hash(body):
            raise SeasonObjectIntegrityError("season storage returned a different object digest")
    return content_hash(root)
