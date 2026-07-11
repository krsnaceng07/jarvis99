"""
PHASE: 45 (M6.4.A)
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md  (§4.4 Distributed Execution)

IMPLEMENTATION PLAN:
    docs/108_PHASE_45_IMPLEMENTATION_PLAN.md  (M6.4.A — transports package)

AUTHORITATIVE:
    NO

Module role: transport-agnostic surface for cross-process task routing.

Exports ``MissionTransport`` (the Protocol) + ``LocalTransport`` (the
in-process implementation) + a ``RemoteTransport`` placeholder (raises
``NotImplementedError``; landed in M6.4.B).

The router (``core/mission/distributed_router.py``) imports ONLY from this
``__init__`` — never from a concrete module — to enforce the "no concrete
import" rule of plan §3 M6.4.A.
"""

from __future__ import annotations

from core.mission.mission_transport import (
    LeaseLostError,
    MissionTransport,
    TransportClosedError,
    TransportError,
)
from core.mission.transports.local import LocalTransport
from core.mission.transports.redis import RemoteTransport

__all__ = [
    "LeaseLostError",
    "LocalTransport",
    "MissionTransport",
    "RemoteTransport",
    "TransportClosedError",
    "TransportError",
]
