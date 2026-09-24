"""Offline whole-capture import with no raw-store I/O inside database transactions."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime

from edgeeagle_domain.raw import RawPayloadReference, RawPayloadStore
from edgeeagle_ingestion.odds_acceptance import OddsCaptureRepository, capture_identity
from edgeeagle_ingestion.odds_guards import OddsEventGuard
from edgeeagle_ingestion.odds_manifest import OddsCaptureManifest
from edgeeagle_ingestion.odds_normalization import (
    NormalizedOddsCapture,
    normalize_odds_capture,
    replay_odds_capture,
)
from edgeeagle_ingestion.odds_receipts import decode_odds_receipt, encode_odds_receipt
from edgeeagle_ingestion.odds_references import OddsReferenceReads
from edgeeagle_ingestion.service import OfflineDatasetImporter, ingest_raw

OddsCaptureTransactions = Callable[[], AbstractContextManager[OddsCaptureRepository]]


@dataclass(frozen=True)
class OddsImportResult:
    raw: RawPayloadReference
    capture_id: str
    inserted_receipts: int


def accept_retained_odds_capture(
    store: RawPayloadStore,
    capture: NormalizedOddsCapture,
    transactions: OddsCaptureTransactions,
) -> OddsImportResult:
    """Verify retained bytes/context before writes; return only after successful commit.

    No current mapping lookup occurs. The transaction factory must commit on clean
    exit and roll back on errors. This is a local orchestration port, not an API.
    """
    body = encode_odds_receipt(capture)
    value = decode_odds_receipt(body)
    replay_odds_capture(store, value)
    identity = capture_identity(value)
    with transactions() as repository:
        inserted = repository.accept(value)
        if type(inserted) is not int or inserted not in (0, 1):
            raise ValueError("invalid accepted capture count")
        retained = repository.get(identity)
        if retained is None or encode_odds_receipt(retained) != body:
            raise ValueError("accepted Odds API receipt differs from verified capture")
    return OddsImportResult(value.manifest.raw, identity, inserted)


def import_odds_capture(
    importer: OfflineDatasetImporter,
    store: RawPayloadStore,
    manifest: OddsCaptureManifest,
    guards: tuple[OddsEventGuard, ...],
    reads: OddsReferenceReads,
    transactions: OddsCaptureTransactions,
    *,
    as_of: datetime,
) -> OddsImportResult:
    """Retain all raw bytes, pin references, normalize, then accept atomically.

    The caller declares the exact expected raw reference in the manifest. Failed
    validation can leave retained raw evidence, never a partially accepted prefix.
    No live acquisition, reference creation, rights inference or publication.
    """
    reference = ingest_raw(importer, store)
    if reference != manifest.raw:
        raise ValueError("retained capture differs from declared manifest")
    value = normalize_odds_capture(store, manifest, guards, reads, as_of=as_of)
    return accept_retained_odds_capture(store, value, transactions)
