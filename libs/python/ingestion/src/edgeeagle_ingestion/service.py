"""Retain acquired bytes before any provider-specific parsing or canonical effects."""

from typing import Protocol

from edgeeagle_domain.raw import (
    RawPayload,
    RawPayloadIntegrityError,
    RawPayloadReference,
    RawPayloadStore,
)


class OfflineDatasetImporter(Protocol):
    """Acquire a bounded local payload, without parsing or inferring knowledge time."""

    def read(self) -> RawPayload: ...


def ingest_raw(importer: OfflineDatasetImporter, store: RawPayloadStore) -> RawPayloadReference:
    """Read once and retain once; failures propagate without hidden retries."""
    payload = importer.read()
    if not isinstance(payload, RawPayload):
        raise TypeError("importer must return a RawPayload")
    reference = store.put(payload)
    if reference != payload.reference():
        raise RawPayloadIntegrityError("storage receipt does not match acquired payload")
    return reference
