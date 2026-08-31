from __future__ import annotations

import asyncio
import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse

from rag_pipeline.api.routes import admin, documents, queries
from rag_pipeline.core.config import Settings, get_settings
from rag_pipeline.core.errors import AppError
from rag_pipeline.core.logging import configure_logging
from rag_pipeline.core.paths import StoragePaths
from rag_pipeline.db.base import Base
from rag_pipeline.db.session import create_engine, create_session_factory

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    configure_logging(settings.log_level)

    paths = StoragePaths(settings.storage_dir)
    paths.ensure()

    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)

    # This prototype intentionally uses create_all for its local SQLite schema.
    # It is not a substitute for a production migration lifecycle.
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    app.state.paths = paths
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.ingestion_semaphore = asyncio.Semaphore(settings.max_concurrent_ingestions)
    try:
        yield
    finally:
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    app = FastAPI(
        title="Construction Document RAG",
        version="0.2.0",
        lifespan=lifespan,
    )
    app.state.settings = active_settings

    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=active_settings.parsed_allowed_hosts(),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.parsed_cors_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Demo-Key", "X-Admin-Key", "X-Request-ID"],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", "")
        if not request_id or len(request_id) > 64:
            request_id = secrets.token_hex(12)
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        payload = {
            "code": exc.code,
            "message": exc.message,
            "request_id": request.state.request_id,
        }
        if exc.details:
            payload["details"] = exc.details
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException):
        message = exc.detail if isinstance(exc.detail, str) else "Request rejected."
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": "http_error",
                "message": message,
                "request_id": request.state.request_id,
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception):
        logger.exception(
            "Unhandled request error request_id=%s path=%s",
            request.state.request_id,
            request.url.path,
        )
        return JSONResponse(
            status_code=500,
            content={
                "code": "internal_error",
                "message": "Internal server error.",
                "request_id": request.state.request_id,
            },
        )

    app.include_router(admin.router, prefix="/v1/admin", tags=["admin"])
    app.include_router(documents.router, prefix="/v1/documents", tags=["documents"])
    app.include_router(queries.router, prefix="/v1/documents", tags=["queries"])

    @app.get("/v1")
    async def root():
        return {"name": "construction-document-rag", "status": "ok"}

    return app


app = create_app()
