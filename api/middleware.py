"""
PHASE: 14
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/76_PHASE_14_API_GATEWAY_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/721908f6-e992-4e3d-9eca-2fca584e321e/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import time
import uuid
from datetime import datetime, timezone
from typing import Tuple

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from api.dto import ErrorDetail, ErrorEnvelope, MetaBlock
from core.exceptions import (
    AuthenticationError,
    BudgetExceededError,
    JarvisAgentError,
    JarvisError,
    JarvisMemoryError,
    JarvisSkillError,
    JarvisSystemError,
    RateLimitError,
    TimeoutError,
)


def map_exception_to_envelope(
    exc: Exception, request_id: uuid.UUID
) -> Tuple[int, ErrorEnvelope]:
    """Map standard and unhandled exceptions to frozen ErrorEnvelopes.

    Ensures that sensitive information (stack traces, paths, credentials)
    is sanitized and never leaked to the client.
    """
    timestamp = datetime.now(timezone.utc)
    meta = MetaBlock(timestamp=timestamp, request_id=request_id)

    if isinstance(exc, RequestValidationError):
        # Map FastAPI validation errors
        detail = ErrorDetail(
            code="VALIDATION_ERROR",
            message="Request validation failed.",
            details={"errors": exc.errors()},
        )
        return 422, ErrorEnvelope(error=detail, meta=meta)

    elif isinstance(exc, JarvisError):
        # Determine status code
        status_code = 500
        if isinstance(exc, JarvisSystemError):
            status_code = 500
        elif isinstance(exc, JarvisMemoryError):
            status_code = 503
        elif isinstance(exc, JarvisAgentError):
            status_code = 422
        elif isinstance(exc, JarvisSkillError):
            status_code = 500
        elif isinstance(exc, BudgetExceededError):
            status_code = 402
        elif isinstance(exc, RateLimitError):
            status_code = 429
        elif isinstance(exc, AuthenticationError):
            status_code = 401
        elif isinstance(exc, TimeoutError):
            status_code = 504

        # Sanitize details (C7 constraint)
        sanitized_details = {}
        for k, v in exc.details.items():
            if k not in (
                "stack_trace",
                "filepath",
                "path",
                "credential",
                "password",
                "token",
                "secret",
                "key",
            ):
                sanitized_details[k] = v

        detail = ErrorDetail(
            code=exc.code, message=exc.message, details=sanitized_details
        )
        return status_code, ErrorEnvelope(error=detail, meta=meta)

    else:
        # Sanitize unhandled exceptions
        detail = ErrorDetail(
            code="SYSTEM_999",
            message="An internal system error occurred.",
            details={},
        )
        return 500, ErrorEnvelope(error=detail, meta=meta)


class RequestStateMiddleware(BaseHTTPMiddleware):
    """Middleware executing request ID tracing and latency calculations."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = uuid.uuid4()
        request.state.request_id = request_id

        start_time = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            # Fail-safe catching of unhandled route-level exceptions
            status_code, envelope = map_exception_to_envelope(exc, request_id)
            response = JSONResponse(
                status_code=status_code, content=envelope.model_dump(mode="json")
            )

        process_time = time.perf_counter() - start_time
        response.headers["X-Request-ID"] = str(request_id)
        response.headers["X-Response-Time"] = f"{process_time * 1000:.2f}ms"
        return response


def register_exception_handlers(app: FastAPI) -> None:
    """Register mapping hooks for validation, domain, and unhandled errors."""

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> Response:
        request_id = getattr(request.state, "request_id", uuid.uuid4())
        status_code, envelope = map_exception_to_envelope(exc, request_id)
        return JSONResponse(
            status_code=status_code, content=envelope.model_dump(mode="json")
        )

    @app.exception_handler(JarvisError)
    async def jarvis_exception_handler(request: Request, exc: JarvisError) -> Response:
        request_id = getattr(request.state, "request_id", uuid.uuid4())
        status_code, envelope = map_exception_to_envelope(exc, request_id)
        return JSONResponse(
            status_code=status_code, content=envelope.model_dump(mode="json")
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> Response:
        request_id = getattr(request.state, "request_id", uuid.uuid4())
        status_code, envelope = map_exception_to_envelope(exc, request_id)
        return JSONResponse(
            status_code=status_code, content=envelope.model_dump(mode="json")
        )
