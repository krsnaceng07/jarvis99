"""
PHASE: 45 (M6.4.C — STRETCH)
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md
        (§4.4 Distributed Execution — leader election; §10 single-DC scope)
    docs/cr/CR-4_phase45_d4_d5_idempotency_envelope.md
        (CR-4, APPROVED 2026-07-09)

IMPLEMENTATION PLAN:
    docs/108_PHASE_45_IMPLEMENTATION_PLAN.md
        (§3 M6.4.C — leader election stretch + horizontal scaling tests)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.

``LeaderElection`` — leader-election state machine layered on top of
``MissionTransport.lease`` / ``renew_lease`` / ``release_lease``.

The state machine:

    CANDIDATE ──try_acquire()──► LEADER (token held)         [True]
                ──try_acquire()──► FOLLOWER (someone else)   [False]

    LEADER     ──renew()──► LEADER        (lease extended)   [True]
                ──renew()──► STEPPED_DOWN  (lease lost)      [False]

    LEADER     ──release()──► RELEASED   (voluntary)
    STEPPED_DOWN              ─► STEPPED_DOWN (terminal)
    RELEASED                   ─► RELEASED  (terminal)
    FOLLOWER     ──try_acquire()──► LEADER | FOLLOWER

    Any state  ──transport closed──► CLOSED (terminal)

Why a separate module (not part of ``DistributedRouter``):

* Per A-1 architect invariant, ``DistributedRouter`` speaks only to the
  ``MissionTransport`` Protocol. Leader election is a separate concern
  (multi-leader deployments) that does not belong in the router itself.
* Per spec §4.4, the shipped M6.4.B default is "single-leader with
  operator-controlled failover (the user restarts the leader)". M6.4.C
  adds the *optional* multi-leader capability; integration with
  ``DistributedRouter`` is a future sub-milestone (out of M6.4.C scope).

Split-brain prevention:

Two ``LeaderElection`` instances racing for the same ``lease_key`` will
see exactly one ``try_acquire()`` return ``True`` (the lease holder);
the other returns ``False`` and stays in ``FOLLOWER``. The guarantee
rests on the underlying ``MissionTransport.lease`` primitive — both
``LocalTransport`` (in-process) and ``RemoteTransport`` (Redis
``SET NX EX``) implement the SETNX-or-fail semantics that prevent
two concurrent acquisitions of the same key.

Degraded mode (per spec §6.4 R7):

If the transport becomes unavailable mid-campaign, the existing leader's
in-process state is not invalidated — it just can't ``renew()`` the
lease. The candidate's local ``role`` transitions to ``CLOSED`` on the
next ``renew()`` call, and the lease naturally expires in the backing
store. A new candidate can then take over once the transport is back.
This is the documented "single-leader continues, no failover" behavior;
it is not enforced in code (no Redis connection = no renew possible),
and is documented in spec §6.4 R7.

Single-DC scope (per spec §10):

Multi-region leader election is explicitly out of scope (a future
``6.6 Multi-region Federation`` goal). M6.4.C covers single-DC leader
election only.
"""

from __future__ import annotations

import asyncio
import enum
import logging
import uuid
from typing import Optional

from core.mission.mission_transport import MissionTransport

logger = logging.getLogger("jarvis.core.mission.leader_election")


# ---------------------------------------------------------------------------
# Public state enum
# ---------------------------------------------------------------------------


class LeaderRole(str, enum.Enum):
    """State in the leader-election lifecycle.

    ``str`` mix-in so the value round-trips through JSON for log lines
    and observability surfaces without a custom encoder.

    States:

    * ``CANDIDATE`` — initial state. ``try_acquire()`` not yet called.
    * ``FOLLOWER`` — ``try_acquire()`` returned ``False``; another holder
      has the lease.
    * ``LEADER`` — this candidate holds the lease (a non-``None`` token).
    * ``STEPPED_DOWN`` — was ``LEADER``; a ``renew()`` returned ``False``
      (lease lost, expired, or stolen). Terminal.
    * ``RELEASED`` — was ``LEADER`` (or any non-terminal); called
      ``release()`` voluntarily. Terminal.
    * ``CLOSED`` — the underlying transport was closed. Terminal.
    """

    CANDIDATE = "CANDIDATE"
    FOLLOWER = "FOLLOWER"
    LEADER = "LEADER"
    STEPPED_DOWN = "STEPPED_DOWN"
    RELEASED = "RELEASED"
    CLOSED = "CLOSED"


# Roles from which a follow-up ``try_acquire()`` is permitted. Used both
# as a guard inside the implementation and as documentation in the
# state diagram. ``FOLLOWER`` and ``CANDIDATE`` can re-attempt; the
# terminal states (``LEADER``, ``STEPPED_DOWN``, ``RELEASED``, ``CLOSED``)
# cannot (a new ``LeaderElection`` instance must be created).
_RE_ACQUIRABLE: frozenset[LeaderRole] = frozenset(
    {LeaderRole.CANDIDATE, LeaderRole.FOLLOWER}
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class LeaderElectionError(Exception):
    """Raised on misuse (re-acquire after release, campaign() from a
    non-CANDIDATE role, etc.). Invalid lease arguments are the
    constructor's responsibility.
    """


# ---------------------------------------------------------------------------
# LeaderElection
# ---------------------------------------------------------------------------


class LeaderElection:
    """Leader-election state machine on a single lease key.

    The class is single-shot: one ``LeaderElection`` instance is one
    candidate in one election cycle. After stepping down, releasing, or
    seeing the transport close, create a new instance to re-elect.

    Parameters
    ----------
    transport : MissionTransport
        The transport to use. Must be open. May be ``LocalTransport``
        (in-process tests) or ``RemoteTransport`` (Redis-backed
        production). The constructor type-checks against the
        ``MissionTransport`` Protocol; concrete transport classes are
        never imported here.
    lease_key : str
        The key to elect on. All candidates contending for the same key
        are part of the same election. The key is the user-facing logical
        name — the transport may prefix it (e.g. ``RemoteTransport`` adds
        ``"jarvis:lease:"`` by default).
    ttl_seconds : int
        The lease TTL in seconds. Must be ``> 0``. Candidates are
        expected to renew at roughly ``ttl_seconds / 3`` intervals; this
        module does not enforce the cadence — the caller chooses
        ``renew_interval`` for ``campaign()``.
    candidate_id : str, optional
        An identifier for this candidate. Used in log lines. Defaults to
        a fresh ``uuid4().hex``.
    """

    # Renewals per lease TTL — the standard "3-strikes" cadence. The
    # leader renews 3 times before a lease would naturally expire.
    _DEFAULT_RENEW_DIVISOR: float = 3.0

    def __init__(
        self,
        transport: MissionTransport,
        lease_key: str,
        ttl_seconds: int,
        *,
        candidate_id: Optional[str] = None,
    ) -> None:
        if not isinstance(lease_key, str) or not lease_key:
            raise LeaderElectionError("lease_key must be a non-empty str.")
        if not isinstance(ttl_seconds, int) or ttl_seconds <= 0:
            raise LeaderElectionError("ttl_seconds must be a positive int.")
        if transport.is_closed:
            raise LeaderElectionError("transport is closed.")
        self._transport: MissionTransport = transport
        self._lease_key: str = lease_key
        self._ttl_seconds: int = ttl_seconds
        self._candidate_id: str = candidate_id or uuid.uuid4().hex
        self._role: LeaderRole = LeaderRole.CANDIDATE
        self._token: Optional[str] = None

    # ----- Properties -------------------------------------------------------

    @property
    def role(self) -> LeaderRole:
        """The current state in the leader-election lifecycle."""
        return self._role

    @property
    def token(self) -> Optional[str]:
        """The held lease token, or ``None`` if not ``LEADER``."""
        return self._token

    @property
    def candidate_id(self) -> str:
        """The candidate identifier (for log lines / observability)."""
        return self._candidate_id

    @property
    def is_leader(self) -> bool:
        """``True`` iff this candidate currently holds the lease."""
        return self._role == LeaderRole.LEADER

    @property
    def lease_key(self) -> str:
        """The lease key this candidate is contending for."""
        return self._lease_key

    @property
    def ttl_seconds(self) -> int:
        """The lease TTL this candidate is using (seconds)."""
        return self._ttl_seconds

    # ----- State transitions ------------------------------------------------

    async def try_acquire(self) -> bool:
        """Single attempt to acquire the lease.

        Returns ``True`` and transitions to ``LEADER`` on success (a
        non-``None`` token is now held).

        Returns ``False`` and transitions to ``FOLLOWER`` if the lease
        is currently held by another candidate (the transport's
        ``lease()`` returned ``None``).

        Raises ``LeaderElectionError`` if the candidate is in a
        terminal state (LEADER, STEPPED_DOWN, RELEASED) — create a new
        ``LeaderElection`` instance to re-elect.

        Side effect: if the transport was closed between construction
        and this call, transitions to ``CLOSED`` and returns ``False``
        (does not raise). Per the MissionTransport contract, ``lease()``
        on a closed transport returns ``None``; we collapse that into
        the ``CLOSED`` role for cleaner observability.
        """
        if self._role not in _RE_ACQUIRABLE:
            raise LeaderElectionError(
                f"Cannot try_acquire from role {self._role.value}; "
                "create a new LeaderElection instance."
            )
        if self._transport.is_closed:
            self._role = LeaderRole.CLOSED
            self._token = None
            return False
        token = await self._transport.lease(self._lease_key, self._ttl_seconds)
        if token is None:
            self._role = LeaderRole.FOLLOWER
            self._token = None
            return False
        self._token = token
        self._role = LeaderRole.LEADER
        logger.info(
            "LeaderElection[%s] acquired lease %r (ttl=%ds) — LEADER.",
            self._candidate_id,
            self._lease_key,
            self._ttl_seconds,
        )
        return True

    async def renew(self) -> bool:
        """Renew the lease if currently ``LEADER``.

        Returns ``True`` on success (still ``LEADER``).

        Returns ``False`` and transitions to ``STEPPED_DOWN`` if the
        lease was lost (expired, released, or stolen by another token).

        Returns ``False`` (without state change) if not currently
        ``LEADER``.

        Side effect: if the transport was closed mid-campaign,
        transitions to ``CLOSED`` and returns ``False``.
        """
        if self._role != LeaderRole.LEADER:
            return False
        if self._transport.is_closed:
            self._role = LeaderRole.CLOSED
            self._token = None
            return False
        assert self._token is not None  # invariant: LEADER ↔ token
        ok = await self._transport.renew_lease(
            self._lease_key,
            self._token,
            self._ttl_seconds,
        )
        if not ok:
            self._role = LeaderRole.STEPPED_DOWN
            self._token = None
            logger.warning(
                "LeaderElection[%s] lost lease %r — STEPPED_DOWN.",
                self._candidate_id,
                self._lease_key,
            )
        return ok

    async def release(self) -> None:
        """Voluntarily release the lease.

        Idempotent. If currently ``LEADER``, calls the transport's
        ``release_lease()`` and transitions to ``RELEASED``. If not
        ``LEADER``, transitions to ``RELEASED`` without touching the
        transport (no lease to release).

        Safe to call when the transport is closed — does not raise.
        """
        if self._role == LeaderRole.LEADER and self._token is not None:
            if not self._transport.is_closed:
                await self._transport.release_lease(self._lease_key, self._token)
            logger.info(
                "LeaderElection[%s] released lease %r — RELEASED.",
                self._candidate_id,
                self._lease_key,
            )
        self._token = None
        if self._role in (
            LeaderRole.LEADER,
            LeaderRole.STEPPED_DOWN,
            LeaderRole.FOLLOWER,
            LeaderRole.CANDIDATE,
        ):
            self._role = LeaderRole.RELEASED

    # ----- Long-running campaign loop --------------------------------------

    async def campaign(
        self,
        *,
        renew_interval: Optional[float] = None,
        max_iterations: Optional[int] = None,
    ) -> LeaderRole:
        """Run the full election cycle: ``try_acquire`` then renew until stepped down.

        Parameters
        ----------
        renew_interval : float, optional
            Seconds between renew attempts. Defaults to
            ``ttl_seconds / 3`` (the standard 3-strikes cadence).
            Must be ``> 0`` if provided.
        max_iterations : int, optional
            Maximum number of renew attempts before returning. Useful
            for tests (avoid an infinite loop in CI). ``None`` (default)
            runs forever until the lease is lost or the task is
            cancelled.

        Returns
        -------
        LeaderRole
            The terminal role:

            * ``FOLLOWER`` — initial ``try_acquire()`` failed.
            * ``LEADER`` — ``max_iterations`` hit while still holding
              the lease.
            * ``STEPPED_DOWN`` — a ``renew()`` returned ``False``.

        Raises
        ------
        LeaderElectionError
            If called from any state other than ``CANDIDATE``.

        Notes
        -----
        On ``asyncio.CancelledError``, the lease is released
        gracefully (best-effort) before the cancellation propagates.
        """
        if self._role != LeaderRole.CANDIDATE:
            raise LeaderElectionError(
                f"campaign() can only be called from CANDIDATE "
                f"(current: {self._role.value})."
            )
        interval: float
        if renew_interval is None:
            interval = self._ttl_seconds / self._DEFAULT_RENEW_DIVISOR
        else:
            if not isinstance(renew_interval, (int, float)) or renew_interval <= 0:
                raise LeaderElectionError(
                    f"renew_interval must be a positive number "
                    f"(got {renew_interval!r})."
                )
            interval = float(renew_interval)
        acquired = await self.try_acquire()
        if not acquired:
            return self._role
        iteration = 0
        try:
            while True:
                if max_iterations is not None and iteration >= max_iterations:
                    return LeaderRole.LEADER
                iteration += 1
                await asyncio.sleep(interval)
                ok = await self.renew()
                if not ok:
                    return self._role
        except asyncio.CancelledError:
            # Graceful shutdown: release the lease if we still hold it.
            await self.release()
            raise


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


__all__ = [
    "LeaderElection",
    "LeaderElectionError",
    "LeaderRole",
]
