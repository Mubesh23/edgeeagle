"""Application construction without database, cloud, or provider side effects."""

from collections.abc import Awaitable, Callable
from typing import Literal

from fastapi import FastAPI, Request, Response
from pydantic import BaseModel

from edgeeagle_api.datasets import DatasetReads
from edgeeagle_api.datasets import router as datasets_router
from edgeeagle_api.events import EventReads, router
from edgeeagle_api.markets import MarketReads
from edgeeagle_api.markets import router as markets_router


class HealthResponse(BaseModel):
    """Process liveness only; this does not assert dependency readiness."""

    status: Literal["ok"] = "ok"


def create_app(
    *,
    event_reads: EventReads | None = None,
    dataset_reads: DatasetReads | None = None,
    market_reads: MarketReads | None = None,
) -> FastAPI:
    """Create an isolated application for serving or in-process tests."""
    app = FastAPI(title="EdgeEagle API", version="0.0.0")
    app.state.event_reads = event_reads
    app.state.dataset_reads = dataset_reads
    app.state.market_reads = market_reads
    app.include_router(router)
    app.include_router(datasets_router)
    app.include_router(markets_router)

    @app.middleware("http")
    async def private_catalog_cache_policy(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        if request.url.path == "/v1/datasets" or request.url.path.startswith("/v1/datasets/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health", response_model=HealthResponse, operation_id="get_health")
    async def health() -> HealthResponse:
        return HealthResponse()

    return app


app = create_app()
