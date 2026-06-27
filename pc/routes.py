"""JARVIS OS - PC Controller API Routing.

Exposes REST endpoints for mouse clicks, keyboard text, clipboard, and shell actions.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from pc.action import (
    ClickAction,
    ClipboardAction,
    KeyAction,
    MoveAction,
    PCAction,
    ShellAction,
)
from pc.controller import PCController

router = APIRouter(prefix="/api/v1/pc", tags=["pc"])

_global_controller: Optional[PCController] = None


def set_routing_context(controller: PCController) -> None:
    """Configure routing context references for endpoints."""
    global _global_controller
    _global_controller = controller


def get_controller() -> PCController:
    """Dependency helper resolving active PCController."""
    if not _global_controller:
        raise HTTPException(status_code=503, detail="PC Controller is not initialized.")
    return _global_controller


class ActionRequest(BaseModel):
    """Payload to request cursor click or keyboard type actions."""

    action_type: str  # 'click', 'move_to', 'key_press', 'clipboard_write'
    x: Optional[int] = None
    y: Optional[int] = None
    button: Optional[str] = "left"
    double_click: Optional[bool] = False
    key: Optional[str] = None
    text: Optional[str] = None


class ShellRequest(BaseModel):
    """Payload to request local terminal shell execution."""

    command: str
    timeout: Optional[float] = 10.0
    work_dir: Optional[str] = None


@router.post("/action")
async def execute_pc_action(
    req: ActionRequest, controller: PCController = Depends(get_controller)
) -> Dict[str, Any]:
    """Route mouse, keyboard, and clipboard executions."""
    try:
        action: PCAction
        if req.action_type == "click":
            if req.x is None or req.y is None:
                raise HTTPException(
                    status_code=400, detail="Click coordinate arguments missing."
                )
            action = ClickAction(
                x=req.x,
                y=req.y,
                button=req.button or "left",
                double_click=req.double_click or False,
            )

        elif req.action_type == "move_to":
            if req.x is None or req.y is None:
                raise HTTPException(status_code=400, detail="Move coordinates missing.")
            action = MoveAction(x=req.x, y=req.y)

        elif req.action_type == "key_press":
            if req.key is None:
                raise HTTPException(status_code=400, detail="Key parameter missing.")
            action = KeyAction(key=req.key, action_type="press")

        elif req.action_type == "clipboard_write":
            if req.text is None:
                raise HTTPException(
                    status_code=400, detail="Clipboard content missing."
                )
            action = ClipboardAction(action="write", content=req.text)

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported action category '{req.action_type}'.",
            )

        res = await controller.execute_action(action)
        if res.get("status") == "DENIED":
            raise HTTPException(status_code=403, detail=res.get("message"))
        return res

    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        raise HTTPException(status_code=400, detail=str(err))


@router.post("/shell")
async def execute_shell(
    req: ShellRequest, controller: PCController = Depends(get_controller)
) -> Dict[str, Any]:
    """Route terminal shell commands."""
    try:
        action = ShellAction(
            command=req.command, timeout=req.timeout or 10.0, work_dir=req.work_dir
        )
        res = await controller.execute_action(action)
        if res.get("status") == "DENIED":
            raise HTTPException(status_code=403, detail=res.get("message"))
        return res
    except HTTPException as http_err:
        raise http_err
    except Exception as err:
        raise HTTPException(status_code=400, detail=str(err))
