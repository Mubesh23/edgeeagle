"""Test-only clock composition: Docker and host wall clocks need not agree."""

from collections.abc import Callable
from datetime import datetime

from sqlalchemy import Engine, text


def database_clock(engine: Engine) -> Callable[[], datetime]:
    """Use the lease authority's live clock; close each read before broker I/O.

    Do not freeze at claimed_at or clamp skew: elapsed lease time still matters.
    Production clock guards are unchanged and tested separately with explicit skew.
    """

    def now() -> datetime:
        with engine.connect() as connection:
            connection.execute(text("SET LOCAL statement_timeout = '5s'"))
            value = connection.scalar(text("SELECT clock_timestamp()"))
            assert isinstance(value, datetime) and value.utcoffset() is not None
            return value

    return now
