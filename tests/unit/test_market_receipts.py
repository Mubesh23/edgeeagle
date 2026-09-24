import hashlib
import json
from dataclasses import replace
from decimal import Decimal, localcontext
from unittest.mock import Mock

import pytest

from edgeeagle_ingestion.market_receipts import decode_market_receipt, encode_market_receipt
from edgeeagle_ingestion.synthetic_markets import normalize_market_fixture, replay_market_fixture
from tests.unit.test_event_normalization import fixture_payload
from tests.unit.test_market_normalization import context


def test_round_trip_preserves_retained_context_and_replay() -> None:
    raw, store = fixture_payload(), Mock()
    store.get.return_value = raw.body
    candidate = normalize_market_fixture(store, raw.reference(), (context(),))[0]
    encoded = encode_market_receipt(candidate)
    assert hashlib.sha256(encoded).hexdigest() == (
        "a327ec2658dd16fad36846740533aaf40b5d0387a0a9fec8293f2db60b365e1f"
    )
    assert decode_market_receipt(encoded) == candidate
    assert encode_market_receipt(decode_market_receipt(encoded)) == encoded
    assert replay_market_fixture(store, (decode_market_receipt(encoded),)) == (candidate,)
    doc = json.loads(encoded)
    assert doc["format"] == 1 and doc["usage"] == "SYNTHETIC_ONLY"
    assert doc["candidate"]["quotes"][0]["available_at"] is None
    with localcontext() as ctx:
        ctx.prec = 2
        precise = replace(
            candidate,
            quotes=(
                replace(
                    candidate.quotes[0], odds_decimal=Decimal("2.12345678901234567890123456789")
                ),
                *candidate.quotes[1:],
            ),
        )
        assert decode_market_receipt(encode_market_receipt(precise)) == precise


@pytest.mark.parametrize(
    "change",
    ["format", "parser_version", "normalizer_version", "usage", "extra", "nested", "quote"],
)
def test_changed_or_unknown_receipt_fields_fail(change: str) -> None:
    raw, store = fixture_payload(), Mock()
    store.get.return_value = raw.body
    candidate = normalize_market_fixture(store, raw.reference(), (context(),))[0]
    doc = json.loads(encode_market_receipt(candidate))
    if change == "extra":
        doc["unexpected"] = True
    elif change == "nested":
        doc["candidate"]["binding"]["event"]["home"]["extra"] = "bad"
    elif change == "quote":
        doc["candidate"]["quotes"][0]["quote_id"]["value"] = "wrong"
    else:
        doc[change] = "unsupported"
    with pytest.raises(ValueError):
        decode_market_receipt(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode())


@pytest.mark.parametrize(
    "body",
    [
        b"{}",
        b"null",
        b"[]",
        b"NaN",
        b"[",
        b"\xff",
        b'{"format":1,"format":1}',
        b" " * (1024 * 1024 + 1),
    ],
)
def test_invalid_receipt_bytes_fail(body: bytes) -> None:
    with pytest.raises(ValueError):
        decode_market_receipt(body)


def test_noncanonical_bytes_and_duplicate_collections_fail() -> None:
    raw, store = fixture_payload(), Mock()
    store.get.return_value = raw.body
    candidate = normalize_market_fixture(store, raw.reference(), (context(),))[0]
    encoded = encode_market_receipt(candidate)
    with pytest.raises(ValueError):
        decode_market_receipt(encoded + b"\n")
    doc = json.loads(encoded)
    doc["candidate"]["binding"]["source"]["capabilities"] *= 2
    with pytest.raises(ValueError):
        decode_market_receipt(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode())
    reordered = replace(
        candidate,
        quotes=tuple(reversed(candidate.quotes)),
        selections=tuple(reversed(candidate.selections)),
    )
    assert encode_market_receipt(reordered) == encoded


@pytest.mark.parametrize(
    "field,value",
    [
        ("odds_decimal", 2.1),
        ("odds_decimal", "bad"),
        ("odds_decimal", "NaN"),
        ("observed_at", 123),
        ("ingested_at", None),
        ("odds_decimal", True),
    ],
)
def test_invalid_typed_scalars(field: str, value: object) -> None:
    raw, store = fixture_payload(), Mock()
    store.get.return_value = raw.body
    c = normalize_market_fixture(store, raw.reference(), (context(),))[0]
    doc = json.loads(encode_market_receipt(c))
    doc["candidate"]["quotes"][0][field] = value
    with pytest.raises(ValueError):
        decode_market_receipt(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode())


def test_collection_types_and_size_limits() -> None:
    raw, store = fixture_payload(), Mock()
    store.get.return_value = raw.body
    c = normalize_market_fixture(store, raw.reference(), (context(),))[0]
    for field in ("quotes", "selections"):
        doc = json.loads(encode_market_receipt(c))
        doc["candidate"][field] = {}
        with pytest.raises(ValueError):
            decode_market_receipt(json.dumps(doc).encode())
    doc = json.loads(encode_market_receipt(c))
    doc["candidate"]["binding"]["source"]["capabilities"] = [1]
    with pytest.raises(ValueError):
        decode_market_receipt(json.dumps(doc).encode())
    with pytest.raises(ValueError, match="size"):
        encode_market_receipt(
            replace(
                c,
                binding=replace(
                    c.binding, source=replace(c.binding.source, code="x" * (1024 * 1024))
                ),
            )
        )


def test_equivalent_decimal_scales_have_identical_receipt_bytes() -> None:
    raw, store = fixture_payload(), Mock()
    store.get.return_value = raw.body
    c = normalize_market_fixture(store, raw.reference(), (context(),))[0]
    padded = replace(
        c,
        quotes=tuple(
            replace(q, odds_decimal=Decimal(str(q.odds_decimal) + "00")) for q in c.quotes
        ),
    )
    assert encode_market_receipt(padded) == encode_market_receipt(c)
