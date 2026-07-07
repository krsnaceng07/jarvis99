"""
PHASE: 27
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/88_PHASE_27_OBSERVABILITY_COST_GOVERNANCE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/89_PHASE_27_IMPLEMENTATION_PLAN.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.

BaseTelemetryBroadcaster abstract interface.

Allows core/ services to broadcast telemetry without direct imports of API/FastAPI components.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from core.observability.dto import TelemetryEnvelope


class BaseTelemetryBroadcaster(ABC):
    """Abstract interface for telemetry broadcasting."""

    @abstractmethod
    async def broadcast(self, envelope: TelemetryEnvelope) -> None:
        """Broadcast a telemetry envelope to all connected clients."""
        pass
