from __future__ import annotations

from collections.abc import AsyncIterator
import secrets

from fastapi import HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from rag_pipeline.core.config import Settings
from rag_pipeline.core.paths import StoragePaths


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_paths(request: Request) -> StoragePaths:
    return request.app.state.paths


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    session_factory = request.app.state.session_factory
    async with session_factory() as session:
        yield session


def require_demo_access(
    request: Request,
) -> None:
    settings: Settings = request.app.state.settings
    if settings.app_mode == "local":
        return
    expected = settings.demo_access_key.get_secret_value() if settings.demo_access_key else ""
    provided = request.headers.get("X-Demo-Key", "")
    if not expected or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing demo access key.")
