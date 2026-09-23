"""Application order and failure boundaries using inward-owned ports only."""

import json
from contextlib import contextmanager
from dataclasses import replace
from typing import Any
from unittest.mock import Mock

import pytest

from edgeeagle_ingestion.football_data_import import import_results_dataset
from tests.unit.test_dataset_manifest import CODEC
from tests.unit.test_fixture_references import NOW
from tests.unit.test_football_data import csv_payload, csv_requests, normalized, resolver


@pytest.mark.parametrize(
    "failure",
    [None, "raw", "accept", "receipt", "changed-receipt", "size", "commit", "manifest", "version"],
)
def test_import_orders_retention_transaction_and_manifest(failure: str | None) -> None:
    order: list[str] = []
    raw, importer, store, repository, manifests = csv_payload(), Mock(), Mock(), Mock(), Mock()
    importer.read.return_value = raw

    def retain(payload: Any) -> Any:
        order.append("raw")
        if failure == "raw":
            raise OSError("retain failed")
        return payload.reference()

    store.put.side_effect = retain
    store.get.return_value = raw.body

    @contextmanager
    def reads() -> Any:
        order.append("read-open")
        yield resolver()
        order.append("read-close")

    values = {v.event.event_id: v for v in normalized()}
    requests = csv_requests()
    if failure == "size":
        requests = tuple(replace(r, context_version="x" * 600_000) for r in requests)
        values = {
            key: replace(value, context_version="x" * 600_000) for key, value in values.items()
        }
    if failure == "changed-receipt":
        values = {key: replace(value, context_version="wrong") for key, value in values.items()}
    repository.get.side_effect = lambda key: None if failure == "receipt" else values[key]
    if failure == "accept":
        repository.accept.side_effect = [True, ValueError("conflict")]

    @contextmanager
    def transactions() -> Any:
        order.append("begin")
        try:
            yield repository
            if failure == "commit":
                raise OSError("commit failed")
        except Exception:
            order.append("rollback")
            raise
        order.append("commit")

    def put(body: bytes) -> str:
        order.append("manifest")
        assert order[-2] == "commit"
        if failure == "manifest":
            raise OSError("manifest failed")
        return "wrong" if failure == "version" else str(json.loads(body)["dataset_version"])

    manifests.put.side_effect = put
    if failure:
        with pytest.raises((ValueError, OSError)):
            import_results_dataset(
                importer, store, requests, reads, transactions, manifests, CODEC, as_of=NOW
            )
        if failure in ("raw", "accept", "receipt", "changed-receipt", "size", "commit"):
            manifests.put.assert_not_called()
        if failure in ("accept", "receipt", "changed-receipt", "size", "commit"):
            assert order[-1] == "rollback"
    else:
        version = import_results_dataset(
            importer, store, csv_requests(), reads, transactions, manifests, CODEC, as_of=NOW
        )
        assert len(version) == 64
        assert order == ["raw", "read-open", "read-close", "begin", "commit", "manifest"]
        assert repository.accept.call_count == repository.get.call_count == 2
    importer.read.assert_called_once()
