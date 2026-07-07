"""JARVIS OS - Phase 27.C TelemetryBroadcaster Tests.

Validates WebSocket connection registration, message queuing, send loop execution,
and lossy queue buffer overflow frame discarding.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from api.broadcaster import TelemetryBroadcaster
from core.observability.dto import TelemetryEnvelope


class MockWebSocket:
    """Simulates FastAPI WebSocket endpoint."""

    def __init__(self, fail_on_send: bool = False) -> None:
        self.accepted: bool = False
        self.sent_messages: list[dict[str, Any]] = []
        self.closed: bool = False
        self._fail_on_send = fail_on_send

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, data: dict[str, Any]) -> None:
        if self.closed:
            raise RuntimeError("Socket is closed")
        if self._fail_on_send:
            raise RuntimeError("Network failure")
        self.sent_messages.append(data)

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def broadcaster() -> TelemetryBroadcaster:
    # Small maxsize=3 for test queue overflow checks
    return TelemetryBroadcaster(queue_maxsize=3)


class TestTelemetryBroadcaster:
    """TelemetryBroadcaster verification suite (Architect constraint C3: lossy queue)."""

    @pytest.mark.asyncio
    async def test_connect_accepts_and_starts_loop(
        self, broadcaster: TelemetryBroadcaster
    ) -> None:
        """connect accepted the socket and registers connection."""
        ws = MockWebSocket()
        await broadcaster.connect(ws)  # type: ignore[arg-type]

        assert ws.accepted is True
        assert broadcaster.active_connection_count == 1

        await broadcaster.disconnect(ws)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_disconnect_cancels_task_and_removes(
        self, broadcaster: TelemetryBroadcaster
    ) -> None:
        """disconnect cleans up the WebSocket registry and cancels background loop."""
        ws = MockWebSocket()
        await broadcaster.connect(ws)  # type: ignore[arg-type]

        await broadcaster.disconnect(ws)  # type: ignore[arg-type]
        assert broadcaster.active_connection_count == 0
        assert ws.closed is True

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_active_sockets(
        self, broadcaster: TelemetryBroadcaster
    ) -> None:
        """broadcast distributes envelope JSON payload to active queues."""
        ws = MockWebSocket()
        await broadcaster.connect(ws)  # type: ignore[arg-type]

        envelope = TelemetryEnvelope(
            active_agents=2,
            queued_tasks=4,
        )
        await broadcaster.broadcast(envelope)
        # Yield execution to sender loop
        await asyncio.sleep(0.05)

        assert len(ws.sent_messages) == 1
        assert ws.sent_messages[0]["active_agents"] == 2
        assert ws.sent_messages[0]["queued_tasks"] == 4

        await broadcaster.disconnect(ws)  # type: ignore[arg-type]

    @pytest.mark.asyncio
    async def test_broadcaster_drops_oldest_on_buffer_overflow(
        self, broadcaster: TelemetryBroadcaster
    ) -> None:
        """If client queue is full (>3), the oldest envelope is discarded (Architect C3)."""
        ws = MockWebSocket()
        await broadcaster.connect(ws)  # type: ignore[arg-type]

        # Stop client sender task temporarily so the queue fills up
        _, task = broadcaster._clients[ws]  # type: ignore[index]
        task.cancel()

        # Enqueue 4 frames (max size is 3)
        await broadcaster.broadcast(TelemetryEnvelope(queued_tasks=1))
        await broadcaster.broadcast(TelemetryEnvelope(queued_tasks=2))
        await broadcaster.broadcast(TelemetryEnvelope(queued_tasks=3))
        # This 4th broadcast should cause queue to overflow and drop the oldest frame (queued_tasks=1)
        await broadcaster.broadcast(TelemetryEnvelope(queued_tasks=4))

        queue, _ = broadcaster._clients[ws]  # type: ignore[index]
        assert queue.qsize() == 3

        items = []
        while not queue.empty():
            items.append(queue.get_nowait())

        # The oldest (queued_tasks=1) was dropped. Values in queue are 2, 3, 4
        assert [item["queued_tasks"] for item in items] == [2, 3, 4]

    @pytest.mark.asyncio
    async def test_disconnection_on_write_failure(
        self, broadcaster: TelemetryBroadcaster
    ) -> None:
        """If send_json fails, client is automatically disconnected."""
        ws = MockWebSocket(fail_on_send=True)
        await broadcaster.connect(ws)  # type: ignore[arg-type]

        await broadcaster.broadcast(TelemetryEnvelope(active_agents=5))
        # Yield to allow sender loop to execute, encounter error, and trigger safe disconnect
        await asyncio.sleep(0.05)

        # Sockets with send failures should be removed from active clients
        assert broadcaster.active_connection_count == 0
