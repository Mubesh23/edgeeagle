"""Explicit loopback-only composition; not a production authentication policy."""

import os
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager

from fastapi import FastAPI
from sqlalchemy import URL, Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

from edgeeagle_api.events import EventReads
from edgeeagle_api.main import create_app
from edgeeagle_api.markets import MarketReads
from edgeeagle_domain.event_query import EventReader
from edgeeagle_domain.market_query import MarketReader
from edgeeagle_persistence.event_query import PostgresEventReader
from edgeeagle_persistence.market_query import PostgresMarketReader


def local_database_url(raw: str) -> URL:
    try:
        url = make_url(raw)
        if (
            url.drivername != "postgresql+psycopg"
            or url.host not in ("127.0.0.1", "::1")
            or not url.database
            or not url.username
            or not url.password
            or url.query
        ):
            raise ValueError("Invalid local configuration")
        return url
    except (ArgumentError, ValueError) as error:
        raise ValueError(
            "Supply a loopback PostgreSQL/psycopg URL without query options"
        ) from error


def event_transactions(engine: Engine) -> EventReads:
    @contextmanager
    def reads() -> Iterator[EventReader]:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            with connection.begin():
                connection.execute(text("SET TRANSACTION READ ONLY"))
                connection.execute(text("SET LOCAL statement_timeout = '5s'"))
                yield PostgresEventReader(connection)

    return reads


def market_transactions(engine: Engine) -> MarketReads:
    @contextmanager
    def reads() -> Iterator[MarketReader]:
        with engine.connect().execution_options(isolation_level="REPEATABLE READ") as connection:
            with connection.begin():
                connection.execute(text("SET TRANSACTION READ ONLY"))
                connection.execute(text("SET LOCAL statement_timeout = '5s'"))
                yield PostgresMarketReader(connection)

    return reads


def create_local_app() -> FastAPI:
    """Uvicorn --factory entry point. Never migrate or seed at startup."""
    url = local_database_url(os.environ.get("EDGEEAGLE_DATABASE_URL", ""))
    app = create_app()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(
            url,
            pool_size=5,
            max_overflow=0,
            pool_timeout=5,
            connect_args={"connect_timeout": 5, "hostaddr": url.host},
        )
        application.state.event_reads = event_transactions(engine)
        application.state.market_reads = market_transactions(engine)
        try:
            yield
        finally:
            application.state.event_reads = None
            application.state.market_reads = None
            engine.dispose()

    app.router.lifespan_context = lifespan
    return app
