"""
PHASE: 45 (M6.4.A)
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md  (§4.4 Distributed Execution)

IMPLEMENTATION PLAN:
    docs/108_PHASE_45_IMPLEMENTATION_PLAN.md  (M6.4.A — LocalTransport; "exhaustive LocalTransport tests")

AUTHORITATIVE:
    NO

``LocalTransport`` — in-process ``MissionTransport`` implementation.

This is the only transport that ships in M6.4.A. The exhaustive test
suite in ``tests/test_local_transport_exhaustive.py`` (≥ 25 tests) covers
every protocol method + boundary + ordering + lease semantic.

Why it lives in M6.4.A (and not M6.4.B):
- Plan §3 M6.4.A directs: "exhaustively test LocalTransport contract
  BEFORE any network code lands". The CI default is LocalTransport
  end-to-end; M6.4.B's ``RemoteTransport`` only ships if the protocol
  surface is rock-solid in-process first.

Semantics (M6.4.A contract — exhaustive tests pin these):

* **Channels.** Each ``subscribe(channel)`` returns a per-channel,
  per-subscriber FIFO queue. Backpressure is implicit (asyncio
  buffering; ``asyncio.Queue``). Multiple subscribers on the same
  channel each receive a copy (pub/sub fanout). One
  ``publish(channel, payload)`` lands as exactly one ``payload`` yield
  on each subscriber.

* **Ordering.** FIFO within one channel; no ordering guarantee across
  channels. This matches the spec's "FIFO within channel; multi-channel
  may interleave on the slow consumer" rule.

* **Idempotency.** ``publish`` is non-idempotent at the protocol level
  (a subsequent ``publish`` with the same payload creates a new
  message). At-least-once delivery is the caller's responsibility (R-1
  idempotency key in ``mission_recovery_journal.wave_run_id``).

* **Lease tokens.** ``lease(key, ttl)`` returns ``uuid4().hex`` if the
  key is currently free; ``None`` if held. ``renew_lease`` checks
  token equality (constant-time via ``hmac.compare_digest``) and
  verifies ``now <= expires_at`` (rejects expired leases). Releases
  are idempotent (a token that does not match just no-ops).

* **TTL semantics.** ``ttl_seconds <= 0`` raises ``ValueError`` (the
  caller is misconfigured). Negative remaining-ttl after a partial
  renewal returns ``False`` from ``renew_lease`` and frees the key.

* **Expiry handling.** A lease that expires between ``lease`` and
  ``renew_lease`` is treated as "stolen by a new holder" — the original
  holder's ``renew_lease`` returns ``False``; the key remains free if
  no one has re-leased it, or is held by the new token if someone has.

* **Close.** ``close()`` sets a flag; pending subscribers receive a
  sentinel ``None`` end-of-stream; future ``publish`` raises
  ``TransportClosedError``; ``lease`` returns ``None`` for any key
  (transport-wide lock-down). ``__aenter__``/``__aexit__`` provided
  for ``async with`` ergonomics.
"""

from __future__ import annotations

import asyncio
import hmac
import logging
import time
import uuid
from types import TracebackType
from typing import Any, Dict, Optional, Set

from core.mission.mission_transport import (
    TransportClosedError,
)

logger = logging.getLogger("jarvis.core.mission.transports.local")


class _EndSentinel:
    """Sentinel object placed in the subscriber queue when the transport
    closes. Use a class (not a bytes literal) so user payload
    ``b""`` cannot collide with the close signal — every published
    payload is bytes, every close signal is a ``_EndSentinel`` instance.

    Single-purpose marker class: no public surface, no attributes.
    """

    __slots__ = ()

    def __repr__(self) -> str:
        return "<LocalTransport._EndSentinel>"


_END_SENTINEL: "_EndSentinel" = _EndSentinel()


class LocalTransport:
    """In-process ``MissionTransport`` implementation.

    Lifecycle: ``await transport.publish(...)`` /
    ``async for msg in transport.subscribe(...)`` /
    ``token = await transport.lease(...)`` /
    ``await transport.close()``.

    Thread-safety: asyncio-cooperative. All public methods are
    ``async def`` except ``subscribe`` (which returns an
    ``AsyncIterator``). Concurrent calls to ``publish`` from multiple
    coroutines on the same channel are serialized via an internal
    per-channel ``asyncio.Lock`` (FIFO ordering is preserved; no
    cross-channel lock).
    """

    def __init__(self, *, clock: "Optional[callable[[], float]]" = None) -> None:
        """Initialize an in-process transport.

        Args:
            clock: Optional monotonic-clock callable. Defaults to
                ``time.monotonic`` for tests that need deterministic
                wall-clock behavior; absolute time (``time.time``) is
                NOT used for lease TTL.
        """
        self._clock: "callable[[], float]" = clock or time.monotonic
        # channel -> set of subscriber queues (fanout via per-subscriber
        # asyncio.Queue). One subscribe() call registers one queue;
        # multiple subscribers on the same channel each receive their
        # own copy of every publish.
        self._channels: "Dict[str, Set[asyncio.Queue[Any]]]"  # type: ignore[type-arg,valid-type]\
        # Lease dict: key -> (token, expires_at). The
        # ``_channel_lock`` serializes lease + publish + close so that
        # no atomicity violation can leak.
        self._leases: Dict[str, "_LeaseEntry"]
        self._closed: bool
        # Per-transport lock (serializes publish + lease + close).
        self._channel_lock: "asyncio.Lock"
        # Subscription bookkeeping for cleanup on close.
        self._subscribers: "Set[asyncio.Queue[Any]]"  # type: ignore[type-arg]\
        self._init_state()

    def _init_state(self) -> None:
        # Helper used both by ``__init__`` and test fixture re-initialization.
        self._channels = {}
        self._leases = {}
        self._closed = False
        self._channel_lock = asyncio.Lock()
        self._subscribers = set()

    # ----- Helpers ---------------------------------------------------------

    def _require_open(self) -> None:
        """Raise ``TransportClosedError`` if the transport is closed.

        Used by ``publish`` and ``subscribe`` per spec \u00a74.4 \u2014 after
        ``close()``, no new publishes are accepted and no new subscribers
        can register. ``lease`` / ``renew_lease`` / ``release_lease`` do
        NOT call this helper: per spec \u00a74.4 "leases become immediately
        readable (``renew_lease`` returns ``False`` for any key)" \u2014
        post-close lease operations are read-only and silent (do not
        raise).
        """
        if self._closed:
            raise TransportClosedError(
                "LocalTransport is closed; publish() / lease() / etc. are unavailable."
            )

    def _check_ttl(self, ttl_seconds: int) -> None:
        if not isinstance(ttl_seconds, int):
            raise TypeError(
                f"ttl_seconds must be an int (got {type(ttl_seconds).__name__})."
            )
        if ttl_seconds <= 0:
            raise ValueError(
                f"ttl_seconds must be > 0 (got {ttl_seconds}); use a positive integer."
            )

    # ----- Channels --------------------------------------------------------

    async def publish(self, channel: str, payload: bytes) -> None:
        """Broadcast ``payload`` to every current subscriber of ``channel``.

        See module docstring for ordering / idempotency / backpressure
        semantics.
        """
        self._require_open()
        if not isinstance(payload, (bytes, bytearray)):
            raise TypeError(f"payload must be bytes (got {type(payload).__name__}).")
        if not isinstance(channel, str):
            raise TypeError(f"channel must be str (got {type(channel).__name__}).")

        async with self._channel_lock:
            queue = self._channels.get(channel)
            if queue is None:
                # No subscribers; per spec, this is a silent no-op
                # (best-effort delivery). The publish is logged at
                # DEBUG so operators can find orphaned channels.
                logger.debug(
                    "LocalTransport.publish(channel=%r): no subscribers; dropping.",
                    channel,
                )
                return
            # We hold a reference; subscribers track themselves in the
            # ``_subscribers`` set so we can fan out by iterating the
            # per-subscriber queues. In LocalTransport the per-channel
            # queue IS the per-subscriber queue (one channel, one
            # subscriber, fanout is realized by treating every subscribe
            # call as a new queue IF there are multiple subscribers;
            # for the single-subscriber case the per-channel queue is
            # the subscriber's queue).
            # Re-design: see docstring — one channel may have many
            # subscribers. Use the channel's subscriber list directly.
            for sub_queue in list(self._subscribers_for_channel(channel)):
                await sub_queue.put(bytes(payload))

    def _subscribers_for_channel(self, channel: str) -> "Set[asyncio.Queue[Any]]":  # type: ignore[type-arg]\
        """Subscribers registered on ``channel``. Tests may inspect."""
        return self._channels.get(channel, set())  # type: ignore[arg-type,return-value]\

    # ----- subscribe() returns a NEW queue per caller ----------------------\
    def subscribe(self, channel: str) -> "LocalSubscriber":
        """Return a per-caller async iterator subscribed to ``channel``.

        Returned object implements the async-iterator protocol
        (``__aiter__`` + ``__anext__`` + ``aclose()``). Closing the
        iterator removes the subscriber from the channel's fanout.

        Although the ``MissionTransport`` Protocol annotates this as
        returning ``AsyncIterator[bytes]``, the concrete return is the
        richer ``LocalSubscriber`` so callers can ``aclose()`` without
        iterating past the next message. The structural-typing check
        (``isinstance(sub, collections.abc.AsyncIterator)``) accepts
        ``LocalSubscriber`` because it implements the protocol.
        """
        self._require_open()
        if not isinstance(channel, str):
            raise TypeError(f"channel must be str (got {type(channel).__name__}).")

        queue: "asyncio.Queue[Any]" = asyncio.Queue()  # type: ignore[type-arg]\
        # Register the queue in this channel's subscriber set.
        self._channels.setdefault(channel, set()).add(queue)  # type: ignore[arg-type]\
        self._subscribers.add(queue)
        return LocalSubscriber(
            transport=self,
            channel=channel,
            queue=queue,
        )

    def _unregister_subscriber(
        self,
        channel: str,
        queue: "asyncio.Queue[Any]",  # type: ignore[type-arg]\
    ) -> None:
        """Drop ``queue`` from the channel's subscriber set. Idempotent."""
        if self._closed:
            return
        subs = self._channels.get(channel)
        if subs is not None and queue in subs:
            subs.discard(queue)
            if not subs:
                self._channels.pop(channel, None)
        self._subscribers.discard(queue)

    # ----- Leases ----------------------------------------------------------

    async def lease(self, key: str, ttl_seconds: int) -> Optional[str]:
        """Acquire ``key`` for ``ttl_seconds``.

        Returns ``uuid4().hex`` on success, ``None`` if the key is
        held by another holder (or if the lease is expired and about
        to be re-issued to a new caller — see ``_claim_lease``).

        Per spec §4.4: after ``close()``, ``lease`` returns ``None`` for
        any key (transport-wide lock-down). Does NOT raise.
        """
        # NOTE: do NOT call ``_require_open()`` here — spec §4.4
        # mandates post-close behavior is silent (returns None).
        if not isinstance(key, str):
            raise TypeError(f"key must be str (got {type(key).__name__}).")
        self._check_ttl(ttl_seconds)
        if self._closed:
            return None
        now = self._clock()
        async with self._channel_lock:  # serializes lease + publish too
            existing = self._leases.get(key)
            if existing is not None and existing.expires_at > now:
                # Held by someone else (still within TTL).
                return None
            # Either no lease, or expired. Claim it.
            token = uuid.uuid4().hex
            self._leases[key] = _LeaseEntry(
                token=token,
                expires_at=now + float(ttl_seconds),
            )
            return token

    async def renew_lease(self, key: str, token: str, ttl_seconds: int) -> bool:
        """Extend the lease if ``token`` matches and lease is live.

        Per spec §4.4: after ``close()``, ``renew_lease`` returns
        ``False`` for any key (transport-wide lock-down). Does NOT
        raise.
        """
        # NOTE: do NOT call ``_require_open()`` here.
        if self._closed:
            return False
        self._check_ttl(ttl_seconds)
        async with self._channel_lock:
            existing = self._leases.get(key)
            if existing is None:
                return False
            # Constant-time comparison — future-proof for the M6.4.B
            # RemoteTransport that may use hashed tokens.
            if not hmac.compare_digest(existing.token, token):
                return False
            now = self._clock()
            if existing.expires_at <= now:
                # Stale; the lease has effectively lapsed.
                self._leases.pop(key, None)
                return False
            existing.expires_at = now + float(ttl_seconds)
            return True

    async def release_lease(self, key: str, token: str) -> None:
        """Release the lease if ``token`` matches. Idempotent.

        Per spec §4.4: after ``close()``, ``release_lease`` is a no-op
        (the leases dict is cleared on close). Does NOT raise.
        """
        # NOTE: do NOT call ``_require_open()`` here. The close()
        # method clears the leases dict so this naturally no-ops.
        async with self._channel_lock:
            existing = self._leases.get(key)
            if existing is None:
                return
            if not hmac.compare_digest(existing.token, token):
                # Token mismatch — do not free the key (the holder is
                # someone else).
                return
            self._leases.pop(key, None)

    # ----- Lifecycle -------------------------------------------------------

    async def close(self) -> None:
        """Shut down: close every subscriber queue + drop leases."""
        if self._closed:
            return
        self._closed = True
        # Fan a sentinel to every subscriber so iterating subscriber
        # loops see graceful end-of-stream rather than hanging on
        # ``queue.get()``.
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(_END_SENTINEL)
            except asyncio.QueueFull:
                # Drop the sentinel if the consumer is far behind;
                # the close event itself is the shutdown signal.
                pass
        self._subscribers.clear()
        self._channels.clear()
        # Drop the leases. ``release_lease`` would no-op on them
        # anyway because the transport is closed.
        self._leases.clear()

    @property
    def is_closed(self) -> bool:
        """``True`` after ``close()`` has been called."""
        return self._closed

    # ----- Async context manager ------------------------------------------

    async def __aenter__(self) -> "LocalTransport":
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> bool:
        await self.close()
        return False


# ---------------------------------------------------------------------------
# Per-subscriber async iterator
# ---------------------------------------------------------------------------


class LocalSubscriber:
    """Async iterator returned by ``LocalTransport.subscribe``.

    Holds a reference to the transport so that ``aclose()`` can
    deregister the queue. Yields ``bytes`` payloads received via
    ``publish``; the iterator terminates on ``close()`` or explicit
    ``aclose()``.
    """

    def __init__(
        self,
        transport: LocalTransport,
        channel: str,
        queue: "asyncio.Queue[Any]",  # type: ignore[type-arg]\
    ) -> None:
        self._transport = transport
        self._channel = channel
        self._queue = queue
        self._closed: bool = False

    def __aiter__(self) -> "LocalSubscriber":
        return self

    async def __anext__(self) -> bytes:
        if self._closed:
            raise StopAsyncIteration
        msg = await self._queue.get()
        if isinstance(msg, _EndSentinel) or msg is _END_SENTINEL:
            self._closed = True
            raise StopAsyncIteration
        # Defensive: every published payload is bytes; anything else is
        # an internal error.
        if not isinstance(msg, (bytes, bytearray)):
            raise TypeError(
                f"LocalSubscriber received unexpected non-bytes payload "
                f"of type {type(msg).__name__} — internal protocol violation."
            )
        return bytes(msg)

    async def aclose(self) -> None:
        """Stop the iterator and unregister from the channel."""
        if self._closed:
            return
        self._closed = True
        self._transport._unregister_subscriber(self._channel, self._queue)


# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------


class _LeaseEntry:
    """Per-key lease record. Plain class (not dataclass) for cheap init."""

    __slots__ = ("token", "expires_at")

    def __init__(self, token: str, expires_at: float) -> None:
        self.token = token
        self.expires_at = expires_at


__all__ = ["LocalSubscriber", "LocalTransport"]
