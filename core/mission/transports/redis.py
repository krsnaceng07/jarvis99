"""
PHASE: 45 (M6.4.B — STUB in M6.4.A landing)
STATUS: STUB
SPECIFICATION:
    docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md  (§4.4 Distributed Execution)

IMPLEMENTATION PLAN:
    docs/108_PHASE_45_IMPLEMENTATION_PLAN.md  (M6.4.B — RemoteTransport over Redis pub/sub + leases)

AUTHORITATIVE:
    NO

``RemoteTransport`` — placeholder module for the M6.4.B Redis-backed
implementation. The module exports ``RemoteTransport`` so type-checkers,
DI containers, and ``core/mission/transports/__init__.py`` re-exports
work end-to-end in M6.4.A — but the class is a stub that raises
``NotImplementedError`` on construction.

The M6.4.A scaffold must not import Redis (per plan §3 line 173:
"Adding ``redis>=5.0`` is deferred to M6.4.B"). The stub itself does
not even ``import redis``.

The class is intentionally a ``RuntimeError``-raising stub so that
mis-configuration (e.g. mistakenly wiring ``RemoteTransport()`` at boot
in M6.4.A) fails loud and early.
"""

from __future__ import annotations

from types import TracebackType
from typing import AsyncIterator, Optional


class RemoteTransport:
    """M6.4.B placeholder.

    Construction raises ``NotImplementedError`` to surface accidental
    wiring in M6.4.A. The real implementation lands in M6.4.B and
    supports all 5 ``MissionTransport`` methods over Redis pub/sub +
    SETNX leases.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError(
            "RemoteTransport is M6.4.B scope; do not instantiate during "
            "M6.4.A. See docs/108_PHASE_45_IMPLEMENTATION_PLAN.md §3 M6.4.B."
        )

    # Protocol surface — declared (with stubs) so ``isinstance(...)``
    # checks against ``MissionTransport`` succeed at type-check time.

    async def publish(self, channel: str, payload: bytes) -> None:  # pragma: no cover
        raise NotImplementedError

    def subscribe(self, channel: str) -> AsyncIterator[bytes]:  # pragma: no cover
        raise NotImplementedError
        yield  # type: ignore[unreachable]  # noqa: E501 — keeps this an async generator

    async def lease(
        self, key: str, ttl_seconds: int
    ) -> Optional[str]:  # pragma: no cover
        raise NotImplementedError

    async def renew_lease(
        self, key: str, token: str, ttl_seconds: int
    ) -> bool:  # pragma: no cover
        raise NotImplementedError

    async def release_lease(self, key: str, token: str) -> None:  # pragma: no cover
        raise NotImplementedError

    async def close(self) -> None:  # pragma: no cover
        raise NotImplementedError

    async def __aenter__(self) -> "RemoteTransport":  # pragma: no cover
        raise NotImplementedError

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> bool:  # pragma: no cover
        raise NotImplementedError


__all__ = ["RemoteTransport"]
