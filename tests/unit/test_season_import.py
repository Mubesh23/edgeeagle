"""Season import is atomic in PostgreSQL; object publication follows commit."""

from contextlib import contextmanager
from dataclasses import replace
from typing import Any
from unittest.mock import Mock

import pytest

from edgeeagle_ingestion.football_data_season_import import import_season_dataset
from edgeeagle_ingestion.season_bundle import content_hash, decode_root
from tests.unit.test_dataset_manifest import CODEC
from tests.unit.test_fixture_references import NOW
from tests.unit.test_football_data_season import season_batch, season_resolver


@pytest.mark.parametrize(
    "failure",
    [
        None,
        "raw",
        "parse",
        "accept",
        "receipt",
        "changed",
        "size",
        "commit",
        "page",
        "root",
        "page-ack",
        "root-ack",
    ],
)
def test_season_import_boundaries_and_order(failure: str | None) -> None:
    raw, requests = season_batch(65)
    order: list[str] = []
    importer, store, repository, objects = Mock(), Mock(), Mock(), Mock()
    if failure == "parse":
        raw = replace(raw, body=raw.body + b"malformed\n")
    if failure == "size":
        requests = tuple(replace(r, context_version="x" * 20_000) for r in requests)
    importer.read.return_value = raw

    def put_raw(payload: Any) -> Any:
        order.append("raw")
        if failure == "raw":
            raise OSError("retention failed")
        return payload.reference()

    store.put.side_effect = put_raw
    store.get.return_value = raw.body

    @contextmanager
    def reads() -> Any:
        order.append("read-open")
        yield season_resolver()
        order.append("read-close")

    accepted: dict[Any, Any] = {}

    def accept(candidate: Any) -> bool:
        if failure == "accept" and len(accepted) == 64:
            raise ValueError("final conflict")
        accepted[candidate.event.event_id] = candidate
        return True

    def get(key: Any) -> Any:
        value = accepted[key]
        if failure == "receipt":
            return None
        return replace(value, context_version="changed") if failure == "changed" else value

    repository.accept.side_effect = accept
    repository.get.side_effect = get

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

    written: list[bytes] = []

    def put(body: bytes) -> str:
        assert "commit" in order and "rollback" not in order
        kind = "root" if b'"kind":"FOOTBALL_DATA_SEASON_INDEX"' in body else "page"
        order.append(kind)
        written.append(body)
        if failure == kind:
            raise OSError("publication failed")
        return "wrong" if failure == kind + "-ack" else content_hash(body)

    objects.put.side_effect = put
    if failure:
        with pytest.raises((ValueError, OSError)):
            import_season_dataset(
                importer, store, requests, reads, transactions, objects, CODEC, as_of=NOW
            )
        if failure in ("raw", "parse", "accept", "receipt", "changed", "size", "commit"):
            objects.put.assert_not_called()
        if failure in ("accept", "receipt", "changed", "size", "commit"):
            assert order[-1] == "rollback"
        if failure in ("raw", "parse"):
            assert "begin" not in order
        if failure in ("page", "page-ack"):
            assert order[-1] == "page" and "root" not in order
    else:
        version = import_season_dataset(
            importer,
            store,
            tuple(reversed(requests)),
            reads,
            transactions,
            objects,
            CODEC,
            as_of=NOW,
        )
        assert version == content_hash(written[-1])
        assert decode_root(written[-1]).page_hashes == tuple(map(content_hash, written[:-1]))
        assert order == [
            "raw",
            "read-open",
            "read-close",
            "begin",
            "commit",
            "page",
            "page",
            "root",
        ]
        assert repository.accept.call_count == repository.get.call_count == 65
        assert list(accepted) == sorted(accepted, key=lambda key: key.value)
    repository.accept_with_notification.assert_not_called()
    importer.read.assert_called_once()
