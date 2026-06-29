"""
PHASE: 14
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/76_PHASE_14_API_GATEWAY_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/721908f6-e992-4e3d-9eca-2fca584e321e/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import uuid
from typing import List, Set, Tuple

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from api.dependencies import get_event_bus
from core.events.base import EventBus
from core.interfaces import InterAgentMessage

router = APIRouter()

# Whitelisted event topics that can be forwarded to WebSocket clients
WHITELIST_TOPICS = [
    "engine.state.transition",
    "workflow.started",
    "workflow.completed",
    "workflow.step.started",
    "workflow.step.completed",
    "workflow.step.failed",
    "system.kernel.ready",
    "tool.spawn.started",
    "tool.completed",
    "tool.failed",
    "tool.approval.waiting",
]


@router.websocket("/telemetry")
async def telemetry_hub(
    websocket: WebSocket,
    event_bus: EventBus = Depends(get_event_bus),
) -> None:
    """ws://host/ws/v1/telemetry endpoint.

    Manages interactive full-duplex WebSocket connections, allowing clients to
    subscribe to specific run_id telemetry events broadcast from the core EventBus.
    """
    await websocket.accept()

    subscribed_runs: Set[uuid.UUID] = set()
    sub_ids: List[Tuple[str, str]] = []

    async def on_event(msg: InterAgentMessage) -> None:
        """Callback triggered on new EventBus messages."""
        body = msg.body or {}
        run_id_str = body.get("run_id")
        if not run_id_str:
            return

        try:
            run_id = uuid.UUID(str(run_id_str))
        except ValueError:
            return

        if run_id in subscribed_runs:
            # WebSocket frame format (Constraint C3): {event, payload, timestamp}
            frame = {
                "event": msg.action,
                "payload": body,
                "timestamp": (
                    msg.timestamp.isoformat()
                    if hasattr(msg.timestamp, "isoformat")
                    else str(msg.timestamp)
                ),
            }
            try:
                await websocket.send_json(frame)
            except Exception:
                # Connection might be closed, handled by the receiver loop
                pass

    # Register subscription callback for each whitelisted topic
    for topic in WHITELIST_TOPICS:
        try:
            sub_id = await event_bus.subscribe(topic, on_event)
            sub_ids.append((topic, sub_id))
        except Exception:
            pass

    try:
        while True:
            # Full-duplex client commands: { "action": "subscribe"|"unsubscribe", "run_id": "<UUID>" }
            data = await websocket.receive_json()
            action = data.get("action")
            run_id_str = data.get("run_id")
            if not action or not run_id_str:
                continue

            try:
                run_id = uuid.UUID(run_id_str)
            except ValueError:
                continue

            if action == "subscribe":
                subscribed_runs.add(run_id)
            elif action == "unsubscribe":
                subscribed_runs.discard(run_id)

    except WebSocketDisconnect:
        pass
    finally:
        # Cleanup: unsubscribe all event bus callbacks
        for topic, sub_id in sub_ids:
            try:
                if hasattr(event_bus, "unsubscribe"):
                    await event_bus.unsubscribe(topic, sub_id)
            except Exception:
                pass
        try:
            await websocket.close()
        except Exception:
            pass
