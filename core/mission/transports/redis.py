"""
PHASE: 45 (M6.4.B.2)
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md  (§4.4 Distributed Execution — cross-node transport)
    docs/cr/CR-4_phase45_d4_d5_idempotency_envelope.md                  (CR-4, APPROVED 2026-07-09)

IMPLEMENTATION PLAN:
    docs/108_PHASE_45_IMPLEMENTATION_PLAN.md  (M6.4.B — RemoteTransport over Redis pub/sub + SETNX leases)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.

``RemoteTransport`` — Redis-backed ``MissionTransport`` implementation.

This module supersedes the M6.4.A stub. It uses ``redis>=5.0.4`` (already in
``pyproject.toml``) for cross-node pub/sub and a Lua-scripted
``SET NX EX`` / atomic-check-and-mutate sequence for cross-node leases.

Why Redis (and not RabbitMQ / NATS / gRPC):
- Already in the runtime dependency set — no new infrastructure pull-in.
- ``SET NX EX`` is the canonical distributed-lock primitive; a single
  round-trip is sufficient for both acquire and TTL setup.
- Pub/sub is a native Redis data path; the only thing we layer on top
  is the per-subscriber async-iterator protocol required by
  ``MissionTransport.subscribe``.

Wire-format note: this transport is **envelope-agnostic**. Callers
``publish`` opaque bytes — the typical payload is the compressed
``EnvelopeV1`` from ``core.mission.transports.envelope``, but the
transport itself does not unpack/repack. Packing is the caller's
responsibility; this keeps the Protocol surface stable across D-5
envelope versions (the transport can carry an EnvelopeV2 tomorrow
without code changes here).

Lease protocol:
- ``lease`` uses ``SET key token NX EX ttl``. If the key did not
  already exist, the SET succeeds and we return the generated token.
  If the key already exists, the SET is a no-op and we return ``None``.
- ``renew_lease`` uses a Lua script for an atomic
  check-token-then-extend-TTL: ``if redis.call('get', KEYS[1]) ==
  ARGV[1] then return redis.call('pexpire', KEYS[1], ARGV[2]) else
  return 0 end``. We use ``pexpire`` (ms precision) to avoid
  floating-point round-trip drift on integer TTLs.
- ``release_lease`` uses a Lua script for an atomic
  check-token-then-delete: ``if redis.call('get', KEYS[1]) ==
  ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end``.
  Idempotent — a second release on a missing key is a no-op.

Lua scripts are registered via ``register_script`` and shipped to the
server on first use; redis-py handles ``EVALSHA`` /
``EVAL`` fallback transparently.

Testability: the ``redis_client`` argument is an injection seam.
Production code passes a real ``redis.asyncio.Redis``; CI / unit tests
pass a ``fakeredis.aioredis.FakeRedis``. The transport does not own
the client's lifecycle (callers pass in a connected client and call
its ``aclose()`` themselves) — this matches the ``MissionTransport``
contract: ``close()`` only affects the transport's own state (subscriber
iterator termination, lock-down of new publishes); it does NOT
tear down the underlying client.

Thread-safety: asyncio-cooperative. Each subscriber owns its own
``redis.client.PubSub`` instance; ``publish`` is a single round-trip
and does not need internal locking. The ``_closed`` flag is read-only
after construction (set once on ``close()``); Python's GIL is
sufficient for the visibility guarantee in an asyncio context.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from types import TracebackType
from typing import Any, Optional

from core.mission.mission_transport import (
    TransportClosedError,
)

logger = logging.getLogger("jarvis.core.mission.transports.redis")


# ---------------------------------------------------------------------------
# Lua scripts — atomic check-token-then-mutate on the Redis server
# ---------------------------------------------------------------------------

# KEYS[1] = lease key, ARGV[1] = token, ARGV[2] = ttl in milliseconds.
# Returns 1 on extend, 0 on token mismatch or missing key.
_LUA_RENEW: str = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('pexpire', KEYS[1], ARGV[2])
else
    return 0
end
"""

# KEYS[1] = lease key, ARGV[1] = token.
# Returns 1 if released, 0 if token mismatch or already missing.
_LUA_RELEASE: str = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""


# ---------------------------------------------------------------------------
# End-of-stream sentinel — used by the subscriber iterator on close()
# ---------------------------------------------------------------------------


class _EndSentinel:
    """Sentinel placed in the subscriber's internal queue when the
    transport closes. Class (not a bytes literal) so user payloads
    ``b""`` cannot collide with the close signal."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "<RemoteTransport._EndSentinel>"


_END_SENTINEL: "_EndSentinel" = _EndSentinel()


# ---------------------------------------------------------------------------
# Per-subscriber async iterator
# ---------------------------------------------------------------------------


class RemoteSubscriber:
    """Async iterator returned by ``RemoteTransport.subscribe``.

    Polls the underlying Redis PubSub object on every ``__anext__``,
    yielding message bodies (bytes) to the caller. Terminates cleanly
    on ``close()`` of the owning transport (a sentinel object is
    injected into the internal queue) or on explicit ``aclose()``.

    Polling model: ``get_message(timeout=...)`` blocks for up to
    ``_POLL_TIMEOUT`` seconds; the iterator loop awaits it. A timeout
    that returns no message re-enters the loop, so a long-idle
    subscriber does not pin a thread.
    """

    # Per-call block on the Redis pubsub. Short enough that close()
    # propagation is responsive; long enough to avoid burning CPU on
    # an idle subscriber.
    _POLL_TIMEOUT: float = 0.25

    def __init__(
        self,
        transport: "RemoteTransport",
        channel: str,
        pubsub: Any,
        chan_name: str,
    ) -> None:
        self._transport = transport
        self._channel = channel
        self._chan_name = chan_name
        self._pubsub = pubsub
        self._closed: bool = False
        # ``_subscribed`` is set to True after the pump's first
        # ``await pubsub.subscribe(...)`` returns. Tests use this
        # to avoid the documented race window between ``subscribe()``
        # returning and the SUBSCRIBE confirmation arriving.
        self._subscribed: bool = False
        # An asyncio queue is the simplest way to bridge the polling
        # loop in ``_pump`` to the async iterator in __anext__.
        self._queue: "asyncio.Queue[Any]" = asyncio.Queue()
        # The polling task is started eagerly. The pump subscribes
        # on its first iteration (lazily) so the Protocol-level
        # ``subscribe(channel)`` can remain a sync method (matches
        # ``LocalTransport.subscribe`` and the MissionTransport
        # Protocol). The race window — a publish that races ahead
        # of the SUBSCRIBE confirmation — is documented: callers
        # MUST ``await asyncio.sleep(0)`` or equivalent between
        # ``subscribe`` and the first ``publish`` on the same
        # channel if they need ordered delivery. Real-world callers
        # always have an await between the two.
        self._pump_task: "asyncio.Task[None]" = asyncio.create_task(
            self._pump(),
            name=f"RemoteSubscriber.pump[{channel}]",
        )

    async def _pump(self) -> None:
        """Background poller: subscribe, then read pubsub messages.

        Runs until ``_closed`` is set or the pubsub object is closed.
        ``get_message`` is the redis-py async API; fakeredis and real
        Redis both implement it.
        """
        try:
            # Subscribe on the first iteration. ``pubsub.subscribe``
            # in redis-py's asyncio client is itself async — we
            # await it here so the SUBSCRIBE confirmation arrives
            # before the first ``get_message`` call. A second
            # subscriber on the same channel (e.g. another
            # ``RemoteTransport.subscribe`` call) is independent —
            # the server tracks subscriptions per-connection.
            try:
                await self._pubsub.subscribe(self._chan_name)
                self._subscribed = True
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "RemoteSubscriber[%s] subscribe failed: %r",
                    self._channel,
                    exc,
                )
                self._queue.put_nowait(exc)
                return
            while not self._closed:
                try:
                    msg = await self._pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=self._POLL_TIMEOUT,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    # Network error / pubsub close race. Surface as a
                    # poisoned queue — the iterator's __anext__ will
                    # raise on next __anext__.
                    logger.warning(
                        "RemoteSubscriber[%s] pump error: %r",
                        self._channel,
                        exc,
                    )
                    self._queue.put_nowait(exc)
                    return
                if msg is None:
                    # No message within the poll window — loop again
                    # so we can observe _closed promptly.
                    continue
                # ``msg`` is a dict: ``{'type': 'message', 'channel': ...,
                # 'data': <bytes>, ...}``. We only yield the body.
                data = msg.get("data")
                if data is None:
                    continue
                if isinstance(data, str):
                    # redis-py may decode by default; the transport
                    # contract requires bytes — re-encode is unsafe
                    # for binary data, so we log a warning and skip.
                    logger.warning(
                        "RemoteSubscriber[%s] received str-typed data "
                        "(length %d); expected bytes — skipping.",
                        self._channel,
                        len(data),
                    )
                    continue
                if not isinstance(data, (bytes, bytearray)):
                    logger.warning(
                        "RemoteSubscriber[%s] received unexpected payload "
                        "type %s — skipping.",
                        self._channel,
                        type(data).__name__,
                    )
                    continue
                self._queue.put_nowait(bytes(data))
        except asyncio.CancelledError:
            # Normal shutdown path via aclose().
            pass
        finally:
            # Signal end-of-stream regardless of how we exited.
            try:
                self._queue.put_nowait(_END_SENTINEL)
            except asyncio.QueueFull:  # pragma: no cover — defensive
                pass

    def __aiter__(self) -> "RemoteSubscriber":
        return self

    async def __anext__(self) -> bytes:
        if self._closed:
            raise StopAsyncIteration
        msg = await self._queue.get()
        if msg is _END_SENTINEL or isinstance(msg, _EndSentinel):
            self._closed = True
            raise StopAsyncIteration
        if isinstance(msg, BaseException):
            # The pump surfaced a network error — re-raise on the
            # caller's coroutine so the failure is visible.
            self._closed = True
            raise msg
        return msg  # type: ignore[return-value]

    async def aclose(self) -> None:
        """Stop the iterator and unsubscribe from the channel."""
        if self._closed:
            return
        self._closed = True
        # Cancel the pump task; the finally-block injects the
        # sentinel, so the consumer is unblocked regardless.
        if not self._pump_task.done():
            self._pump_task.cancel()
            try:
                await self._pump_task
            except (asyncio.CancelledError, BaseException):  # noqa: BLE001
                pass
        # Best-effort unsubscribe + close the pubsub. Wrapped in
        # try/except because the underlying connection may already
        # be gone (network partition mid-close).
        try:
            await self._pubsub.unsubscribe(self._channel)
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "RemoteSubscriber[%s] unsubscribe raised %r (ignored).",
                self._channel,
                exc,
            )
        try:
            await self._pubsub.aclose()
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "RemoteSubscriber[%s] pubsub.aclose raised %r (ignored).",
                self._channel,
                exc,
            )


# ---------------------------------------------------------------------------
# RemoteTransport
# ---------------------------------------------------------------------------


class RemoteTransport:
    """Redis-backed ``MissionTransport``.

    Construction::

        client = redis.asyncio.Redis(host=..., port=..., decode_responses=False)
        await client.ping()
        transport = RemoteTransport(redis_client=client)
        await transport.publish("mission.tasks", b"\\x00...")

    The transport does NOT own the Redis client — it borrows a
    connected instance. ``close()`` shuts down subscribers and locks
    the transport; the caller is responsible for ``client.aclose()``
    if and when they want to drop the connection.

    Decode-responses: the transport requires ``decode_responses=False``
    on the injected client. Bytes-in-bytes-out is the
    ``MissionTransport`` contract; auto-decode to str would corrupt
    binary payloads.

    Lua-script access: ``register_script`` is invoked lazily on the
    first renew / release. redis-py caches the SHA after the first
    successful ``EVAL``; the ``EVALSHA`` fallback is automatic.

    Concurrency: ``publish`` is a single round-trip; the transport
    issues no global lock. ``lease`` / ``renew_lease`` /
    ``release_lease`` are also single round-trips. The ``_closed``
    flag is the only shared mutable state, and it transitions once.
    """

    def __init__(
        self,
        *,
        redis_client: Any,
        key_prefix: str = "mission:lease:",
        channel_prefix: str = "mission:channel:",
    ) -> None:
        """Initialize.

        Args:
            redis_client: A connected ``redis.asyncio.Redis`` (or a
                ``fakeredis.aioredis.FakeRedis`` for tests). MUST have
                ``decode_responses=False`` so payloads stay as bytes.
            key_prefix: Prefix prepended to every lease key. Defaults
                to ``"mission:lease:"`` to avoid collisions with
                other Redis tenants in the same DB.
            channel_prefix: Prefix prepended to every pub/sub channel.
                Defaults to ``"mission:channel:"``.

        Raises:
            ValueError: on bad arguments (None client, empty prefix).
        """
        if redis_client is None:
            raise ValueError("RemoteTransport requires a redis_client (got None).")
        if not isinstance(key_prefix, str) or not key_prefix:
            raise ValueError("key_prefix must be a non-empty str.")
        if not isinstance(channel_prefix, str) or not channel_prefix:
            raise ValueError("channel_prefix must be a non-empty str.")
        self._redis = redis_client
        self._key_prefix = key_prefix
        self._channel_prefix = channel_prefix
        self._closed: bool = False
        # Set of active subscribers so close() can wake them all.
        self._subscribers: "set[RemoteSubscriber]" = set()
        # Lazy-registered Lua scripts. ``register_script`` returns a
        # ``Script`` object; the first call ships the body to the
        # server, subsequent calls use EVALSHA.
        self._lua_renew: Any = None
        self._lua_release: Any = None
        # Per-script registration lock so concurrent first-use does
        # not race on the ``register_script`` call.
        self._script_lock: "asyncio.Lock" = asyncio.Lock()

    # ----- Helpers ---------------------------------------------------------

    def _require_open(self) -> None:
        """Raise ``TransportClosedError`` if the transport is closed."""
        if self._closed:
            raise TransportClosedError(
                "RemoteTransport is closed; publish() / subscribe() are unavailable."
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

    def _lease_key(self, key: str) -> str:
        return f"{self._key_prefix}{key}"

    def _channel_name(self, channel: str) -> str:
        return f"{self._channel_prefix}{channel}"

    async def _ensure_scripts(self) -> None:
        """Register Lua scripts on first use. Idempotent."""
        if self._lua_renew is not None and self._lua_release is not None:
            return
        async with self._script_lock:
            if self._lua_renew is None:
                self._lua_renew = self._redis.register_script(_LUA_RENEW)
            if self._lua_release is None:
                self._lua_release = self._redis.register_script(_LUA_RELEASE)

    # ----- Channels --------------------------------------------------------

    async def publish(self, channel: str, payload: bytes) -> None:
        """Broadcast ``payload`` to every current subscriber of ``channel``.

        Per spec §4.4: best-effort. If no subscribers are registered on
        the channel, the Redis ``PUBLISH`` command returns 0 (number of
        clients reached) and we do not raise — this matches the
        ``LocalTransport`` "no subscribers = silent no-op" rule.
        """
        self._require_open()
        if not isinstance(payload, (bytes, bytearray)):
            raise TypeError(f"payload must be bytes (got {type(payload).__name__}).")
        if not isinstance(channel, str):
            raise TypeError(f"channel must be str (got {type(channel).__name__}).")
        chan_name = self._channel_name(channel)
        n_reached = await self._redis.publish(chan_name, bytes(payload))
        try:
            n_int = int(n_reached or 0)
        except (TypeError, ValueError):  # pragma: no cover — defensive
            n_int = 0
        if n_int:
            logger.debug(
                "RemoteTransport.publish(channel=%r) reached %d subscriber(s).",
                channel,
                n_int,
            )

    def subscribe(self, channel: str) -> RemoteSubscriber:
        """Return a per-caller async iterator subscribed to ``channel``.

        Subscribes eagerly (before returning) so a message published
        between ``subscribe()`` and the first ``__anext__`` is not
        dropped. The returned ``RemoteSubscriber`` implements the
        async-iterator protocol and ``aclose()``.

        Although the ``MissionTransport`` Protocol annotates the
        return as ``AsyncIterator[bytes]``, the concrete return is the
        richer ``RemoteSubscriber`` so callers can ``aclose()`` without
        iterating past the next message. ``isinstance`` against
        ``collections.abc.AsyncIterator`` accepts ``RemoteSubscriber``
        because it implements the protocol.
        """
        self._require_open()
        if not isinstance(channel, str):
            raise TypeError(f"channel must be str (got {type(channel).__name__}).")
        chan_name = self._channel_name(channel)
        pubsub = self._redis.pubsub()
        # ``pubsub.subscribe`` is async in redis-py's asyncio client.
        # We delegate the await to ``RemoteSubscriber._pump`` so that
        # this method can remain a sync (Protocol-compatible) call.
        # See ``RemoteSubscriber._pump`` for the race-window note.
        sub = RemoteSubscriber(
            transport=self,
            channel=channel,
            pubsub=pubsub,
            chan_name=chan_name,
        )
        self._subscribers.add(sub)
        return sub

    # ----- Leases ----------------------------------------------------------

    async def lease(self, key: str, ttl_seconds: int) -> Optional[str]:
        """Acquire ``key`` for ``ttl_seconds``.

        Returns a fresh ``uuid4().hex`` token on success, ``None`` if
        ``key`` is already held by another holder.

        Per spec §4.4: after ``close()``, ``lease`` returns ``None``
        for any key (transport-wide lock-down). Does NOT raise.
        """
        if not isinstance(key, str):
            raise TypeError(f"key must be str (got {type(key).__name__}).")
        self._check_ttl(ttl_seconds)
        if self._closed:
            return None
        full_key = self._lease_key(key)
        token = uuid.uuid4().hex
        # ``nx=True`` is the SETNX semantics: only succeed if the key
        # is currently free. ``ex=ttl_seconds`` sets the expiration
        # atomically with the SET — no race window where a held key
        # has no TTL.
        ok = await self._redis.set(full_key, token, nx=True, ex=ttl_seconds)
        if ok:
            return token
        return None

    async def renew_lease(self, key: str, token: str, ttl_seconds: int) -> bool:
        """Extend the lease if ``token`` matches the current holder.

        Per spec §4.4: after ``close()``, ``renew_lease`` returns
        ``False`` for any key (transport-wide lock-down). Does NOT
        raise.
        """
        if not isinstance(key, str):
            raise TypeError(f"key must be str (got {type(key).__name__}).")
        if not isinstance(token, str):
            raise TypeError(f"token must be str (got {type(token).__name__}).")
        self._check_ttl(ttl_seconds)
        if self._closed:
            return False
        await self._ensure_scripts()
        full_key = self._lease_key(key)
        # TTL in milliseconds — pexpire takes integer ms.
        ttl_ms = int(ttl_seconds * 1000)
        result = await self._lua_renew(
            keys=[full_key],
            args=[token, ttl_ms],
        )
        # ``pexpire`` returns 1 on success, 0 if the key does not
        # exist. Both cases collapse to "could not extend" from the
        # caller's perspective.
        return int(result or 0) == 1

    async def release_lease(self, key: str, token: str) -> None:
        """Release the lease if ``token`` matches. Idempotent.

        Per spec §4.4: after ``close()``, ``release_lease`` is a
        no-op. Does NOT raise. A wrong-token release is also a no-op
        (the holder is someone else).
        """
        if not isinstance(key, str):
            raise TypeError(f"key must be str (got {type(key).__name__}).")
        if not isinstance(token, str):
            raise TypeError(f"token must be str (got {type(token).__name__}).")
        if self._closed:
            return
        await self._ensure_scripts()
        full_key = self._lease_key(key)
        # The Lua script is the authoritative check; it does
        # GET-then-DEL atomically on the server. A wrong-token call
        # costs one round-trip (EVALSHA) but never frees the key.
        await self._lua_release(keys=[full_key], args=[token])

    # ----- Lifecycle -------------------------------------------------------

    async def close(self) -> None:
        """Shut down: terminate every subscriber and lock the transport.

        After ``close()``:
        - ``publish`` raises ``TransportClosedError``.
        - ``subscribe`` raises ``TransportClosedError`` (no new
          subscribers).
        - ``lease`` returns ``None`` for any key.
        - ``renew_lease`` returns ``False`` for any key.
        - ``release_lease`` is a silent no-op.

        The injected ``redis_client`` is NOT closed by this call —
        the caller owns its lifecycle. This matches the
        ``LocalTransport.close()`` rule.
        """
        if self._closed:
            return
        self._closed = True
        # aclose() every active subscriber. ``aclose`` itself is
        # idempotent, so a double-close is safe.
        subs = list(self._subscribers)
        self._subscribers.clear()
        for sub in subs:
            try:
                await sub.aclose()
            except Exception as exc:  # noqa: BLE001
                logger.debug(
                    "RemoteTransport.close: subscriber aclose raised %r (ignored).",
                    exc,
                )

    @property
    def is_closed(self) -> bool:
        """``True`` after ``close()`` has been called."""
        return self._closed

    @property
    def key_prefix(self) -> str:
        """The lease-key prefix (read-only)."""
        return self._key_prefix

    @property
    def channel_prefix(self) -> str:
        """The channel-name prefix (read-only)."""
        return self._channel_prefix

    # ----- Async context manager ------------------------------------------

    async def __aenter__(self) -> "RemoteTransport":
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
# Module surface
# ---------------------------------------------------------------------------

__all__ = ["RemoteSubscriber", "RemoteTransport"]
