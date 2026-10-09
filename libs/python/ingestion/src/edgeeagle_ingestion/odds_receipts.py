"""Strict whole-capture Odds API receipt v2; separate from legacy market v1."""

import json

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
from .odds_api_parser import PARSER_VERSION, NativeOddsBookmaker, NativeOddsEvent, NativeOddsOutcome
from .odds_normalization import (
    NORMALIZER_VERSION,
    NormalizedOddsCapture,
    _project,
)

MAX_RECEIPT_BYTES = 8 * 1024 * 1024


def _validate(capture: NormalizedOddsCapture) -> None:
    if capture.parser_version != PARSER_VERSION or capture.normalizer_version != NORMALIZER_VERSION:
        raise ValueError("unsupported odds receipt versions")
    if len(capture.evidence) > 100 or len(capture.observations) > 2000:
        raise ValueError("odds capture exceeds bounds")
    observations = {(o.provider_event_id, o.bookmaker_key): o for o in capture.observations}
    if len(observations) != len(capture.observations):
        raise ValueError("duplicate odds observations")
    native = []
    for evidence in capture.evidence:
        guard, refs = evidence.guard, evidence.references
        books = []
        for revision in refs.revisions[2:]:
            key = revision.key.provider_entity_id
            obs = observations.get((guard.event_key.provider_entity_id, key))
            outcomes = []
            book_time = market_time = None
            if obs is not None:
                if len(obs.selections) != 3 or len(obs.quotes) != 3:
                    raise ValueError("receipt must contain complete three-way prices")
                prices = {q.selection_id: q.odds_decimal for q in obs.quotes}
                labels = {"HOME": guard.home_label, "DRAW": "Draw", "AWAY": guard.away_label}
                for selection in obs.selections:
                    outcomes.append(
                        NativeOddsOutcome(
                            labels[selection.outcome.value], prices[selection.selection_id]
                        )
                    )
                book_time, market_time = obs.bookmaker_updated_at, obs.market_updated_at
                for timestamp in (book_time, market_time):
                    if timestamp is not None and timestamp > capture.manifest.snapshot_at:
                        raise ValueError("provider update exceeds snapshot")
            books.append(NativeOddsBookmaker(key, book_time, market_time, tuple(outcomes)))
        native.append(
            NativeOddsEvent(
                guard.event_key.provider_entity_id,
                refs.revisions[0].key.provider_entity_id,
                guard.starts_at,
                guard.home_label,
                guard.away_label,
                tuple(books),
            )
        )
    if sorted(e.guard.event_key.provider_entity_id for e in capture.evidence) != [
        e.event_id for e in native
    ]:
        raise ValueError("noncanonical evidence order")
    if _project(tuple(native), capture.manifest, capture.evidence) != capture:
        raise ValueError("receipt projection is inconsistent")


def _body(capture: NormalizedOddsCapture) -> bytes:
    return json.dumps(
        {"format": 2, "usage": capture.manifest.usage, "capture": _encode(capture)},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def encode_odds_receipt(capture: NormalizedOddsCapture) -> bytes:
    try:
        value = _decode(NormalizedOddsCapture, _encode(capture))
        _validate(value)
        body = _body(value)
        if len(body) > MAX_RECEIPT_BYTES:
            raise ValueError("odds receipt exceeds size limit")
        return body
    except (TypeError, KeyError, AttributeError, RecursionError, ArithmeticError) as exc:
        raise ValueError("invalid odds receipt") from exc


def decode_odds_receipt(body: bytes) -> NormalizedOddsCapture:
    if not isinstance(body, bytes) or len(body) > MAX_RECEIPT_BYTES:
        raise ValueError("odds receipt must be bounded bytes")
    try:
        doc = json.loads(
            body, object_pairs_hook=_pairs, parse_float=_forbidden, parse_constant=_forbidden
        )
        if (
            not isinstance(doc, dict)
            or set(doc) != {"format", "usage", "capture"}
            or type(doc["format"]) is not int
            or doc["format"] != 2
        ):
            raise ValueError("invalid odds receipt envelope")
        capture: NormalizedOddsCapture = _decode(NormalizedOddsCapture, doc["capture"])
        _validate(capture)
        if doc["usage"] != capture.manifest.usage or _body(capture) != body:
            raise ValueError("noncanonical odds receipt")
        return capture
    except (
        TypeError,
        KeyError,
        AttributeError,
        UnicodeError,
        RecursionError,
        ArithmeticError,
    ) as exc:
        raise ValueError("invalid odds receipt") from exc
