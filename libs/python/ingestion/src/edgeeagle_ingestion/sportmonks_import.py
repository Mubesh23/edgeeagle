"""Compose one offline Sportmonks capture through retained receipt acceptance."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime

from edgeeagle_domain.raw import RawPayloadReference, RawPayloadStore

from .service import OfflineDatasetImporter, ingest_raw
from .sportmonks_acceptance import SportmonksReceiptRepository
from .sportmonks_manifest import SportmonksCaptureManifest
from .sportmonks_normalization import NormalizedSportmonksFixture, normalize_sportmonks_capture
from .sportmonks_receipts import (
    encode_sportmonks_receipt,
    replay_sportmonks_receipt,
    sportmonks_capture_identity,
)
from .sportmonks_references import SportmonksReferenceReads

SportmonksReceiptTransactions = Callable[[], AbstractContextManager[SportmonksReceiptRepository]]


@dataclass(frozen=True)
class SportmonksImportResult:
    """Acknowledged private receipt from a completed local import transaction."""

    raw: RawPayloadReference
    capture_id: str
    receipt: NormalizedSportmonksFixture
    inserted_receipts: int


def import_sportmonks_capture(
    importer: OfflineDatasetImporter,
    store: RawPayloadStore,
    manifest: SportmonksCaptureManifest,
    reads: SportmonksReferenceReads,
    transactions: SportmonksReceiptTransactions,
    *,
    as_of: datetime,
) -> SportmonksImportResult:
    """Retain, resolve, replay, accept and verify one authored capture.

    The acquired immutable reference must exactly match the supplied manifest.
    Raw verification, pinned reference resolution and retained-context replay all
    finish before the caller's READ COMMITTED transaction begins. Its context
    commits on clean exit and rolls back on errors. The function returns only
    after commit; S3 and PostgreSQL are not a distributed transaction.
    """
    reference = ingest_raw(importer, store)
    if reference != manifest.raw:
        raise ValueError("acquired Sportmonks raw reference differs from capture manifest")

    candidate = normalize_sportmonks_capture(store, manifest, reads, as_of=as_of)
    return accept_retained_sportmonks_capture(store, candidate, transactions)


def accept_retained_sportmonks_capture(
    store: RawPayloadStore,
    retained: NormalizedSportmonksFixture,
    transactions: SportmonksReceiptTransactions,
) -> SportmonksImportResult:
    """Re-verify and accept original receipt evidence without current references.

    Use this for a retry after mappings or canonical display state have changed.
    The retained receipt's original evidence is replayed from immutable raw before
    opening the acceptance transaction; no fresh normalization is performed.
    """
    receipt = replay_sportmonks_receipt(store, retained)
    body = encode_sportmonks_receipt(receipt)
    capture_id = sportmonks_capture_identity(receipt)

    with transactions() as repository:
        inserted = repository.accept(receipt)
        stored_receipt = repository.get(capture_id)
        if stored_receipt is None or encode_sportmonks_receipt(stored_receipt) != body:
            raise ValueError("accepted Sportmonks receipt differs from normalized capture")

    return SportmonksImportResult(
        raw=receipt.manifest.raw,
        capture_id=capture_id,
        receipt=stored_receipt,
        inserted_receipts=inserted,
    )
