"""Internal structural validation shared by domain records."""

from datetime import datetime


def text(value: object, field: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field} must be a string")
    if not value or value != value.strip():
        raise ValueError(f"{field} must be nonempty and have no surrounding whitespace")


def instance(value: object, expected: type, field: str) -> None:
    if not isinstance(value, expected):
        raise TypeError(f"{field} must be a {expected.__name__}")


def aware_datetime(value: datetime, field: str) -> None:
    instance(value, datetime, field)
    if value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
