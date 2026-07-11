"""
PHASE: 45 (M6.4.A)
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md  (v1.2 FROZEN — §4.4 Distributed Execution)

IMPLEMENTATION PLAN:
    docs/108_PHASE_45_IMPLEMENTATION_PLAN.md  (M6.4.A — MissionTransport protocol + LocalTransport + WorkerProcess)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.

``MissionTransport`` — transport-agnostic surface for cross-process task
routing (per spec §4.4). The leader (``DistributedRouter``) talks to this
protocol only; it never imports a concrete transport class. New transports
(``LocalTransport`` in M6.4.A, ``RemoteTransport`` in M6.4.B) are drop-in
modules under ``core/mission/transports/``.

Why a Protocol here (rather than an ABC):
- Type-check only; not a runtime base class. Implementations can be
  duck-typed (a function-style mock for tests, a struct of async closures
  in M6.4.B's Redis variant, etc.).
- Preserves the "transport-agnostic" promise of §4.4 without forking the
  hierarchy as new transports land.

Method contract (per spec §4.4):

* ``publish(channel, payload)`` — best-effort broadcast on a channel.
  ``payload`` is opaque bytes (the caller is responsible for serialization
  via ``core/mission_serializers.py``; never trust the transport to know
  the message shape).

* ``subscribe(channel)`` — returns an ``AsyncIterator[bytes]`` that yields
  one element per ``publish`` on that channel. Ordering is **FIFO within
  one channel** and **independent across channels** (multi-channel may
  interleave on the slow consumer). Backpressure is the caller's problem:
  the iterator pauses on slow ``__anext__`` consumption.

* ``lease(key, ttl_seconds)`` — leader-elects ``key`` for ``ttl_seconds``.
  Returns the lease token (``str``) if the acquire succeeded, ``None`` if
  the key is currently held by another holder. The lease token is
  ``uuid4().hex`` in ``LocalTransport`` (collision-resistant within one
  process) and is implementation-defined in ``RemoteTransport``.

* ``renew_lease(key, token, ttl_seconds)`` — extends the lease by
  ``ttl_seconds`` only when ``token`` matches the holder recorded for
  ``key``. Returns ``True`` on success, ``False`` if the lease has
  expired, was released, or the token doesn't match (constant-time
  comparison; future-proof for the Redis SETNX variant).

* ``release_lease(key, token)`` — releases the lease if ``token`` matches.
  Idempotent (subsequent releases of an already-released key are no-ops
  and never raise).

* ``close()`` — graceful shutdown. After ``close()``:
  - ``publish`` raises ``TransportClosedError``.
  - ``subscribe`` raises ``TransportClosedError`` (no new subscribers).
  - Existing ``subscribe`` iterators terminate (``StopAsyncIteration``).
  - ``lease`` returns ``None`` for any key (transport-wide lock-down).
  - ``renew_lease`` returns ``False`` for any key.
  - ``release_lease`` is a silent no-op (leases dict was cleared).
  Async context-manager support is opt-in via ``__aenter__``/``__aexit__``
  (overrides accepted).

The protocol has **no** dependencies on ``redis``, ``msgpack``, or any
network stack by design — that is the "LocalTransport-exhaustive first"
contract of plan §3 M6.4.A.
"""

from __future__ import annotations

from types import TracebackType
from typing import AsyncIterator, Optional, Protocol, runtime_checkable


# Custom exceptions — raised by transports; never caught by spec code
# (the leader's responsibility is to retry/drop based on the exception
# class).
class TransportError(Exception):
    """Base for transport-layer errors."""


class TransportClosedError(TransportError):
    """Raised when an operation is attempted on a closed transport."""


class LeaseLostError(TransportError):
    """Raised when a lease has been lost mid-operation (renew or release
    attempted with an expired token)."""


@runtime_checkable
class MissionTransport(Protocol):
    """Transport-agnostic surface for cross-process task routing.

    See module docstring for the full method contract.
    """

    # ----- Channels --------------------------------------------------------

    async def publish(self, channel: str, payload: bytes) -> None:
        """Best-effort broadcast on a channel."""
        ...

    def subscribe(self, channel: str) -> AsyncIterator[bytes]:
        """Subscribe to a channel.

        Returns an ``AsyncIterator[bytes]`` (one element per
        ``publish``). The iterator terminates cleanly on ``close()``
        or on caller ``aclose()``.
        """
        ...

    # ----- Leases (leader election / cross-process locks) -----------------

    async def lease(self, key: str, ttl_seconds: int) -> Optional[str]:
        """Acquire a lease on ``key`` for ``ttl_seconds`` seconds.

        Returns the lease token on success, ``None`` if another holder
        currently owns the lease.
        """
        ...

    async def renew_lease(self, key: str, token: str, ttl_seconds: int) -> bool:
        """Extend the lease on ``key`` if ``token`` matches the holder.

        Returns ``True`` on success, ``False`` if the lease has expired,
        been released, or was held by a different token.
        """
        ...

    async def release_lease(self, key: str, token: str) -> None:
        """Release the lease on ``key`` if ``token`` matches the holder.

        Idempotent — never raises on a missing or already-released key.
        """
        ...

    # ----- Lifecycle -------------------------------------------------------

    async def close(self) -> None:
        """Graceful shutdown. Subsequent ``publish`` raises
        ``TransportClosedError``; outstanding ``subscribe`` iterators
        terminate; ``renew_lease`` returns ``False`` for any key.
        """
        ...

    # ----- Async context manager (opt-in) ---------------------------------
    # Implementations MAY override; default-fall-through is provided by
    # ``async def __aenter__(self): return self`` plus
    # ``async def __aexit__(self, *exc): await self.close(); return False``
    # but the Protocol does not require it. Tests that need a context
    # manager can wrap any ``MissionTransport`` via
    # ``contextlib.AsyncExitStack``.

    async def __aenter__(self) -> "MissionTransport":
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> bool:
        await self.close()
        return False


__all__ = [
    "LeaseLostError",
    "MissionTransport",
    "TransportClosedError",
    "TransportError",
]
