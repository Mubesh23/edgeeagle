"""Retain and normalize a complete authored capture before atomic acceptance."""

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass

from edgeeagle_domain.raw import RawPayloadReference, RawPayloadStore
from edgeeagle_ingestion.market_acceptance import (
    MarketAcceptanceRepository,
    canonical_batch,
    receipt_id,
)
from edgeeagle_ingestion.market_receipts import encode_market_receipt
from edgeeagle_ingestion.service import OfflineDatasetImporter, ingest_raw
from edgeeagle_ingestion.synthetic_markets import MarketFixtureBinding, normalize_market_fixture

MarketAcceptanceTransactions = Callable[[], AbstractContextManager[MarketAcceptanceRepository]]


@dataclass(frozen=True)
class MarketImportResult:
    raw: RawPayloadReference
    receipt_ids: tuple[str, ...]
    inserted_receipts: int


def import_market_fixture(
    importer: OfflineDatasetImporter,
    store: RawPayloadStore,
    bindings: tuple[MarketFixtureBinding, ...],
    transactions: MarketAcceptanceTransactions,
) -> MarketImportResult:
    """Return only after the caller's transaction context successfully commits.

    The context must commit on clean exit and roll back on errors. Retention and
    complete normalization run before entering it; no storage I/O spans database
    writes. Raw objects can survive failed normalization/acceptance and are reused
    on exact retries. No reference creation, publication, repair or live calls.
    """
    reference = ingest_raw(importer, store)
    candidates = canonical_batch(normalize_market_fixture(store, reference, bindings))
    identities = tuple(receipt_id(candidate) for candidate in candidates)
    with transactions() as repository:
        inserted = repository.accept(candidates)
        for identity, expected in zip(identities, candidates, strict=True):
            retained = repository.get(identity)
            if retained is None or encode_market_receipt(retained) != encode_market_receipt(
                expected
            ):
                raise ValueError("accepted market receipt differs from normalized capture")
    return MarketImportResult(reference, identities, inserted)
