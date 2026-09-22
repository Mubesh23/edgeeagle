"""Application construction without database, cloud, or provider side effects."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Process liveness only; this does not assert dependency readiness."""

    status: Literal["ok"] = "ok"


def create_app() -> FastAPI:
    """Create an isolated application for serving or in-process tests."""
    app = FastAPI(title="EdgeEagle API", version="0.0.0")

    @app.get("/health", response_model=HealthResponse, operation_id="get_health")
    async def health() -> HealthResponse:
        return HealthResponse()

    return app


app = create_app()
