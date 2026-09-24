"""Market import ordering and fail-closed acknowledgement without network."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from unittest.mock import Mock

import pytest

from edgeeagle_ingestion.market_acceptance import MarketAcceptanceRepository
from edgeeagle_ingestion.market_import import import_market_fixture
from edgeeagle_ingestion.synthetic_markets import normalize_market_fixture
from tests.unit.test_event_normalization import fixture_payload
from tests.unit.test_market_normalization import context


@pytest.mark.parametrize("failure", [None, "missing", "changed", "commit"])
def test_market_import_orders_storage_before_transaction_and_checks_readback(
    failure: str | None,
) -> None:
    raw, importer, store = fixture_payload(), Mock(), Mock()
    importer.read.return_value = raw
    store.put.return_value = raw.reference()
    store.get.return_value = raw.body
    expected = normalize_market_fixture(store, raw.reference(), (context(),))[0]
    store.reset_mock()
    repository = Mock(spec=MarketAcceptanceRepository)
    repository.accept.return_value = 1
    repository.get.return_value = (
        None
        if failure == "missing"
        else replace(
            expected,
            binding=replace(
                expected.binding,
                event=replace(
                    expected.binding.event,
                    home=replace(expected.binding.event.home, canonical_name="changed"),
                ),
            ),
        )
        if failure == "changed"
        else expected
    )
    events = []

    @contextmanager
    def transactions() -> Iterator[MarketAcceptanceRepository]:
        store.put.assert_called_once_with(raw)
        store.get.assert_called_once_with(raw.reference())
        events.append("enter")
        yield repository
        events.append("commit")
        if failure == "commit":
            raise RuntimeError("commit failed")

    if failure:
        with pytest.raises((ValueError, RuntimeError)):
            import_market_fixture(importer, store, (context(),), transactions)
        assert events == (["enter", "commit"] if failure == "commit" else ["enter"])
    else:
        result = import_market_fixture(importer, store, (context(),), transactions)
        assert result.raw == raw.reference() and result.inserted_receipts == 1
        assert len(result.receipt_ids) == 1
        assert events == ["enter", "commit"]
    store.get.assert_called_once()


def test_market_import_rejects_invalid_final_outcome_before_transaction() -> None:
    raw, importer, store, transactions = fixture_payload(), Mock(), Mock(), Mock()
    raw = replace(raw, body=raw.body.replace(b'"price": 3.2', b'"price": 1'))
    importer.read.return_value = raw
    store.put.return_value = raw.reference()
    store.get.return_value = raw.body
    with pytest.raises(ValueError):
        import_market_fixture(importer, store, (context(),), transactions)
    transactions.assert_not_called()
