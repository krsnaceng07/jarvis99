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

TelemetryBroadcaster WebSocket router.

Architect constraints incorporated:
- C3: Bounded lossy queue (maxsize=100) discarding oldest frames on slow clients.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from fastapi import WebSocket

from core.observability.broadcaster_interface import BaseTelemetryBroadcaster
from core.observability.dto import TelemetryEnvelope

logger = logging.getLogger("api.broadcaster")


class TelemetryBroadcaster(BaseTelemetryBroadcaster):
    """Manages active WebSocket connections and broadcasts telemetry updates.

    Architect constraint C3: Lossy queue per connection. Discards oldest frames.
    """

    def __init__(self, queue_maxsize: int = 100) -> None:
        self._maxsize = queue_maxsize
        self._clients: Dict[
            WebSocket, tuple[asyncio.Queue[Dict[str, Any]], asyncio.Task[None]]
        ] = {}

    async def connect(self, websocket: WebSocket) -> None:
        """Register a new WebSocket client and start its sending loop."""
        await websocket.accept()
        queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=self._maxsize)
        task = asyncio.create_task(self._client_sender_loop(websocket, queue))
        self._clients[websocket] = (queue, task)
        logger.info(
            "Telemetry WebSocket client connected. Active: %d", len(self._clients)
        )

    async def disconnect(self, websocket: WebSocket) -> None:
        """Disconnect and clean up resources for a client."""
        if websocket in self._clients:
            queue, task = self._clients.pop(websocket)
            task.cancel()
            try:
                await websocket.close()
            except Exception:
                pass
            logger.info(
                "Telemetry WebSocket client disconnected. Active: %d",
                len(self._clients),
            )

    async def broadcast(self, envelope: TelemetryEnvelope) -> None:
        """Enqueue the telemetry envelope to all connected clients.

        Architect constraint C3: If a client queue is full, drop the oldest frame.
        """
        payload = envelope.model_dump(mode="json")
        for ws, (queue, _) in list(self._clients.items()):
            if queue.full():
                try:
                    queue.get_nowait()
                    queue.task_done()
                except (asyncio.QueueEmpty, ValueError):
                    pass
                logger.debug("Telemetry queue full for client; dropped oldest frame")

            try:
                queue.put_nowait(payload)
            except Exception as exc:
                logger.warning("Failed to enqueue telemetry frame: %s", exc)

    async def _client_sender_loop(
        self, websocket: WebSocket, queue: asyncio.Queue[Dict[str, Any]]
    ) -> None:
        """Background coroutine to send queued items to a specific client."""
        try:
            while True:
                payload = await queue.get()
                try:
                    await websocket.send_json(payload)
                except Exception as exc:
                    logger.debug(
                        "WebSocket write failed: %s; disconnecting client", exc
                    )
                    break
                finally:
                    queue.task_done()
        except asyncio.CancelledError:
            pass
        finally:
            asyncio.create_task(self._safe_disconnect(websocket))

    async def _safe_disconnect(self, websocket: WebSocket) -> None:
        """Clean up client registration safely."""
        try:
            await self.disconnect(websocket)
        except Exception:
            pass

    @property
    def active_connection_count(self) -> int:
        return len(self._clients)
