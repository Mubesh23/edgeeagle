import json
from dataclasses import replace
from decimal import Decimal, localcontext
from typing import Any

import pytest

from edgeeagle_domain.raw import RawPayload
from edgeeagle_ingestion.odds_normalization import normalize_odds_capture, replay_odds_capture
from edgeeagle_ingestion.odds_receipts import decode_odds_receipt, encode_odds_receipt
from tests.unit.test_odds_manifest import NOW
from tests.unit.test_odds_normalization import inputs


def receipt() -> tuple[Any, bytes, Any]:
    manifest, guard, _, store, _, reads = inputs()
    capture = normalize_odds_capture(store, manifest, (guard,), reads, as_of=NOW)
    return capture, encode_odds_receipt(capture), store


def test_round_trip_exact_decimals_and_retained_replay() -> None:
    capture, body, store = receipt()
    with localcontext() as context:
        context.prec = 3
        restored = decode_odds_receipt(body)
        assert restored == capture
        assert encode_odds_receipt(restored) == body
    replay_odds_capture(store, restored)
    assert b"2.12345678901234567890123456789" in body


@pytest.mark.parametrize(
    "change", ["format", "usage", "version", "extra", "field", "type", "price", "quote_id"]
)
def test_malformed_or_inconsistent_receipt_fails_closed(change: str) -> None:
    _, body, _ = receipt()
    doc = json.loads(body)
    root = doc["capture"]
    if change == "format":
        doc["format"] = True
    if change == "usage":
        doc["usage"] = "REPLAY_ONLY"
    if change == "version":
        root["normalizer_version"] = "unknown"
    if change == "extra":
        doc["extra"] = None
    if change == "field":
        del root["manifest"]["captured_at"]
    if change == "type":
        root["evidence"][0]["references"]["event"]["event_id"]["$type"] = "VenueId"
    if change == "price":
        root["observations"][0]["quotes"][0]["odds_decimal"] = 2.5
    if change == "quote_id":
        root["observations"][0]["quotes"][0]["quote_id"]["value"] = "0" * 64
    with pytest.raises(ValueError):
        decode_odds_receipt(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode())


@pytest.mark.parametrize(
    "body", [b"{}", b"[]", b'{"format":2,"format":2}', b"NaN", b" " * (8 * 1024 * 1024 + 1)]
)
def test_invalid_envelope_and_size_limits(body: bytes) -> None:
    with pytest.raises(ValueError):
        decode_odds_receipt(body)


def test_noncanonical_bytes_and_unvalidated_projection_are_rejected() -> None:
    capture, body, _ = receipt()
    with pytest.raises(ValueError):
        decode_odds_receipt(b" " + body)
    observation = capture.observations[0]
    bad = replace(
        observation,
        quotes=(
            replace(observation.quotes[0], odds_decimal=Decimal("1.01")),
            *observation.quotes[1:],
        ),
    )
    # Prices are authoritative only when checked against raw bytes, but identity,
    # membership and timestamp consistency are enforceable without raw I/O.
    encoded = encode_odds_receipt(replace(capture, observations=(bad,)))
    assert decode_odds_receipt(encoded).observations[0].quotes[0].odds_decimal == Decimal("1.01")
    with pytest.raises(ValueError):
        encode_odds_receipt(
            replace(capture, observations=(replace(observation, quotes=observation.quotes[:2]),))
        )


@pytest.mark.parametrize(
    "case",
    ["literal", "list", "set", "time", "nan", "scalar", "bounds", "duplicate", "future_time"],
)
def test_typed_fields_and_projection_limits(case: str) -> None:
    _, body, _ = receipt()
    doc = json.loads(body)
    capture = doc["capture"]
    manifest = capture["manifest"]
    if case == "literal":
        manifest["market"] = "spread"
    if case == "list":
        capture["evidence"] = {}
    if case == "set":
        capture["evidence"][0]["references"]["source"]["capabilities"] = ["a", "a"]
    if case == "time":
        manifest["raw"]["capture"]["ingested_at"] = 42
    if case == "nan":
        capture["observations"][0]["quotes"][0]["odds_decimal"] = "NaN"
    if case == "scalar":
        capture["evidence"][0]["references"]["revisions"][0]["revision"] = True
    if case == "bounds":
        capture["evidence"] *= 101
    if case == "duplicate":
        capture["observations"] *= 2
    if case == "future_time":
        capture["observations"][0]["bookmaker_updated_at"] = "2099-01-01T00:00:00+00:00"
    with pytest.raises(ValueError):
        decode_odds_receipt(json.dumps(doc, sort_keys=True, separators=(",", ":")).encode())


def test_empty_capture_round_trip_without_reference_reads() -> None:
    from unittest.mock import Mock

    m, _, _, store, _, _ = inputs()
    m = replace(m, raw=RawPayload(capture=m.raw.capture, body=b"[]").reference())
    store.get.return_value = b"[]"
    reads = Mock(side_effect=AssertionError("no reference reads"))
    empty = normalize_odds_capture(store, m, (), reads, as_of=NOW)
    assert decode_odds_receipt(encode_odds_receipt(empty)) == empty
    replay_odds_capture(store, empty)


def test_codec_does_not_replace_raw_integrity_verification() -> None:
    capture, _, store = receipt()
    observation = capture.observations[0]
    changed = replace(
        capture,
        observations=(
            replace(
                observation,
                quotes=(
                    replace(observation.quotes[0], odds_decimal=Decimal("1.01")),
                    *observation.quotes[1:],
                ),
            ),
        ),
    )
    decoded = decode_odds_receipt(encode_odds_receipt(changed))
    with pytest.raises(ValueError, match="replay"):
        replay_odds_capture(store, decoded)
