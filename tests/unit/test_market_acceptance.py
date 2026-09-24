"""Network-free acceptance identity and complete-binding checks."""

from dataclasses import replace
from decimal import Decimal
from unittest.mock import Mock

import pytest

from edgeeagle_domain.provenance import VenueId
from edgeeagle_ingestion.market_acceptance import canonical_batch, receipt_id
from edgeeagle_ingestion.synthetic_markets import normalize_market_fixture
from tests.unit.test_event_normalization import fixture_payload
from tests.unit.test_market_normalization import context


def test_receipt_identity_excludes_price_but_canonical_comparison_does_not() -> None:
    raw, store = fixture_payload(), Mock()
    store.get.return_value = raw.body
    candidate = normalize_market_fixture(store, raw.reference(), (context(),))[0]
    reordered = replace(candidate, quotes=tuple(reversed(candidate.quotes)))
    assert receipt_id(candidate) == receipt_id(reordered)
    assert canonical_batch((candidate,)) == canonical_batch((reordered,))
    changed = replace(
        candidate,
        quotes=(replace(candidate.quotes[0], odds_decimal=Decimal("7")), *candidate.quotes[1:]),
    )
    assert receipt_id(candidate) == receipt_id(changed)
    assert canonical_batch((candidate,)) != canonical_batch((changed,))
    for invalid in ((), (candidate, candidate), (candidate,) * 2001):
        with pytest.raises(ValueError):
            canonical_batch(invalid)
    second = replace(
        candidate.binding.venues[0],
        provider_key="other",
        venue=replace(candidate.binding.venues[0].venue, venue_id=VenueId("other")),
    )
    incomplete = replace(
        candidate,
        binding=replace(candidate.binding, venues=(*candidate.binding.venues, second)),
    )
    with pytest.raises(ValueError, match="coverage"):
        canonical_batch((incomplete,))
