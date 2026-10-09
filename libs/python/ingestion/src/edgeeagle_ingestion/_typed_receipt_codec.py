"""Bounded typed JSON mechanics shared by provider-specific receipt codecs."""

import types
from dataclasses import fields, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from functools import lru_cache
from typing import Any, Literal, get_args, get_origin, get_type_hints

from edgeeagle_domain._validation import aware_datetime


def decimal_text(value: Decimal) -> str:
    """Return a context-independent spelling without expanding huge exponents."""
    if not value.is_finite():
        raise ValueError("nonfinite receipt decimal")
    sign, digits, exponent = value.as_tuple()
    if not isinstance(exponent, int):
        raise ValueError("nonfinite receipt decimal")
    end = len(digits)
    while end > 1 and digits[end - 1] == 0:
        end -= 1
    return str(Decimal((sign, digits[:end], exponent + len(digits) - end)))


@lru_cache(maxsize=64)
def _hints(cls: type) -> dict[str, Any]:
    # Payload tags never select imports, classes or executable code.
    return get_type_hints(cls)


def encode_typed_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            "$type": type(value).__name__,
            **{
                field.name: encode_typed_value(getattr(value, field.name))
                for field in fields(value)
            },
        }
    if isinstance(value, datetime):
        aware_datetime(value, "receipt timestamp")
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Decimal):
        return decimal_text(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [encode_typed_value(item) for item in value]
    if isinstance(value, frozenset):
        return sorted(value)
    if value is None or type(value) in (str, int, bool):
        return value
    raise ValueError("unsupported receipt value")


def decode_typed_value(expected: Any, value: Any, depth: int = 0) -> Any:
    if depth > 32:
        raise ValueError("receipt nesting exceeds limit")
    origin, args = get_origin(expected), get_args(expected)
    if origin is types.UnionType:
        for option in args:
            try:
                return decode_typed_value(option, value, depth + 1)
            except (ValueError, TypeError):
                pass
        raise ValueError("receipt union type mismatch")
    if origin is Literal:
        if not any(type(value) is type(option) and value == option for option in args):
            raise ValueError("unsupported receipt literal")
        return value
    if origin in (tuple, frozenset):
        if not isinstance(value, list) or len(value) > 6000:
            raise ValueError("invalid receipt collection")
        items = tuple(decode_typed_value(args[0], item, depth + 1) for item in value)
        if origin is frozenset:
            if len(set(items)) != len(items):
                raise ValueError("duplicate set members")
            return frozenset(items)
        return items
    if isinstance(expected, type) and is_dataclass(expected):
        hints = _hints(expected)
        if (
            not isinstance(value, dict)
            or set(value) != {"$type", *hints}
            or value["$type"] != expected.__name__
        ):
            raise ValueError("invalid typed receipt record")
        return expected(
            **{
                name: decode_typed_value(kind, value[name], depth + 1)
                for name, kind in hints.items()
            }
        )
    if expected is datetime:
        if not isinstance(value, str):
            raise ValueError("receipt timestamp must be text")
        parsed = datetime.fromisoformat(value)
        aware_datetime(parsed, "receipt timestamp")
        return parsed.astimezone(UTC)
    if expected is Decimal:
        if not isinstance(value, str) or len(value) > 1024:
            raise ValueError("receipt decimal must be bounded exact text")
        number = Decimal(value)
        if not number.is_finite():
            raise ValueError("nonfinite receipt decimal")
        return number
    if isinstance(expected, type) and issubclass(expected, Enum):
        return expected(value)
    if expected in (str, int, bool, type(None)) and type(value) is expected:
        return value
    raise ValueError("invalid receipt scalar")


def unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate receipt key")
        value[key] = item
    return value


def reject_json_number(value: str) -> Any:
    raise ValueError("receipt requires exact decimal strings")
