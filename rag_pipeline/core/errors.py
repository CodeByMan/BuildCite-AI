from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class AppError(Exception):
    code: str
    message: str
    status_code: int = 400
    details: dict[str, Any] | None = None


class ValidationError(AppError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "invalid_request",
        status_code: int = 400,
    ):
        super().__init__(code=code, message=message, status_code=status_code)


class NotFoundError(AppError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(code="not_found", message=message, status_code=404, details=details)


class ConflictError(AppError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(code="conflict", message=message, status_code=409, details=details)


class ConfigError(AppError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(code="config_error", message=message, status_code=503, details=details)


class ProcessingError(AppError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(code="processing_error", message=message, status_code=500, details=details)
