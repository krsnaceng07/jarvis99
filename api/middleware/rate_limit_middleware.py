"""
PHASE: 17
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/78_PHASE_17_AUTHENTICATION_AUTHORIZATION_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/721908f6-e992-4e3d-9eca-2fca584e321e/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import time
import uuid
from collections import deque
from typing import Any, Deque, Dict

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

from api.middleware import map_exception_to_envelope
from core.exceptions import RateLimitError


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware enforcing sliding-window rate limits by IP address for login routes."""

    def __init__(self, app: Any, limit: int = 5, window_seconds: int = 60) -> None:
        """Initialize the rate limiter with custom thresholds."""
        super().__init__(app)
        self.limit = limit
        self.window_seconds = window_seconds
        self.history: Dict[str, Deque[float]] = {}

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Track client IP request rate on sensitive routes and return 429 when throttled."""
        if request.url.path == "/api/v1/auth/login":
            client_ip = request.client.host if request.client else "unknown"
            now = time.time()

            if client_ip not in self.history:
                self.history[client_ip] = deque()

            queue = self.history[client_ip]

            # Clear expired timestamps
            while queue and queue[0] < now - self.window_seconds:
                queue.popleft()

            if len(queue) >= self.limit:
                exc = RateLimitError(
                    code="RATE_001",
                    message="Too many login attempts. Please try again later.",
                )
                request_id = getattr(request.state, "request_id", uuid.uuid4())
                status_code, envelope = map_exception_to_envelope(exc, request_id)
                return JSONResponse(
                    status_code=429, content=envelope.model_dump(mode="json")
                )

            queue.append(now)

        return await call_next(request)
