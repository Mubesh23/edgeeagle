"""Strict Sportmonks observation receipt v1; replay only, with no persistence."""

import hashlib
import json

from edgeeagle_domain.raw import RawPayloadStore

from ._typed_receipt_codec import (
    decode_typed_value as _decode,
)
from ._typed_receipt_codec import (
    encode_typed_value as _encode,
)
from ._typed_receipt_codec import (
    reject_json_number as _forbidden,
)
from ._typed_receipt_codec import (
    unique_json_object as _pairs,
)
from .sportmonks_manifest import read_sportmonks_capture
from .sportmonks_normalization import (
    NORMALIZER_VERSION,
    NormalizedSportmonksFixture,
    _project,
)
from .sportmonks_parser import PARSER_VERSION

RECEIPT_FORMAT = 1
IDENTITY_VERSION = 1
MAX_RECEIPT_BYTES = 8 * 1024 * 1024


def _validate(capture: NormalizedSportmonksFixture) -> None:
    if capture.parser_version != PARSER_VERSION or capture.normalizer_version != NORMALIZER_VERSION:
        raise ValueError("unsupported Sportmonks receipt versions")
    _project(
        capture.manifest,
        capture.native,
        capture.references,
        parser_version=capture.parser_version,
        normalizer_version=capture.normalizer_version,
    )


def _body(capture: NormalizedSportmonksFixture) -> bytes:
    encoded = _encode(capture)
    # Event entries have domain role order for validation; receipts use the
    # specified participant-ID order for representation stability.
    entries = encoded["references"]["entries"]
    entries.sort(key=lambda entry: entry["participant_id"]["value"])
    return json.dumps(
        {"format": RECEIPT_FORMAT, "usage": capture.manifest.usage, "capture": encoded},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def encode_sportmonks_receipt(capture: NormalizedSportmonksFixture) -> bytes:
    """Validate and encode one complete, canonical Sportmonks observation receipt."""
    try:
        value: NormalizedSportmonksFixture = _decode(NormalizedSportmonksFixture, _encode(capture))
        _validate(value)
        body = _body(value)
        if len(body) > MAX_RECEIPT_BYTES:
            raise ValueError("Sportmonks receipt exceeds size limit")
        return body
    except (TypeError, KeyError, AttributeError, RecursionError, ArithmeticError) as exc:
        raise ValueError("invalid Sportmonks receipt") from exc


def decode_sportmonks_receipt(body: bytes) -> NormalizedSportmonksFixture:
    """Decode exact canonical receipt bytes without importing payload-selected types."""
    if not isinstance(body, bytes) or len(body) > MAX_RECEIPT_BYTES:
        raise ValueError("Sportmonks receipt must be bounded bytes")
    try:
        doc = json.loads(
            body, object_pairs_hook=_pairs, parse_float=_forbidden, parse_constant=_forbidden
        )
        if (
            not isinstance(doc, dict)
            or set(doc) != {"format", "usage", "capture"}
            or type(doc["format"]) is not int
            or doc["format"] != RECEIPT_FORMAT
        ):
            raise ValueError("invalid Sportmonks receipt envelope")
        capture: NormalizedSportmonksFixture = _decode(NormalizedSportmonksFixture, doc["capture"])
        _validate(capture)
        if doc["usage"] != capture.manifest.usage or _body(capture) != body:
            raise ValueError("noncanonical Sportmonks receipt")
        return capture
    except (
        TypeError,
        KeyError,
        AttributeError,
        UnicodeError,
        RecursionError,
        ArithmeticError,
    ) as exc:
        raise ValueError("invalid Sportmonks receipt") from exc


def sportmonks_capture_identity(capture: NormalizedSportmonksFixture) -> str:
    """Hash the frozen manifest and transformation versions, excluding projection."""
    try:
        value: NormalizedSportmonksFixture = _decode(NormalizedSportmonksFixture, _encode(capture))
        _validate(value)
        identity = {
            "identity_version": IDENTITY_VERSION,
            "manifest": _encode(value.manifest),
            "parser_version": value.parser_version,
            "normalizer_version": value.normalizer_version,
        }
        body = json.dumps(
            identity,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
        return hashlib.sha256(body).hexdigest()
    except (TypeError, KeyError, AttributeError, RecursionError, ArithmeticError) as exc:
        raise ValueError("invalid Sportmonks capture identity") from exc


def replay_sportmonks_receipt(
    store: RawPayloadStore, capture: NormalizedSportmonksFixture
) -> NormalizedSportmonksFixture:
    """Reproduce a receipt from exact retained raw and its retained mapping context."""
    receipt: NormalizedSportmonksFixture = _decode(NormalizedSportmonksFixture, _encode(capture))
    _validate(receipt)
    native = read_sportmonks_capture(store, receipt.manifest)
    replayed = _project(
        receipt.manifest,
        native,
        receipt.references,
        parser_version=receipt.parser_version,
        normalizer_version=receipt.normalizer_version,
    )
    if _body(replayed) != _body(receipt):
        raise ValueError("Sportmonks replay differs from retained receipt")
    return replayed
