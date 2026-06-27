"""JARVIS OS - PC Automation Action DTOs.

Defines Pydantic models representing keyboard, mouse, clipboard, and shell actions.
"""

from typing import Optional

from pydantic import BaseModel, Field


class PCAction(BaseModel):
    """Base class for all PC automation DTOs."""

    pass


class ClickAction(PCAction):
    """Mouse click action at coordinates (x, y)."""

    x: int = Field(..., description="Horizontal pixel coordinate.")
    y: int = Field(..., description="Vertical pixel coordinate.")
    button: str = "left"
    double_click: bool = False


class MoveAction(PCAction):
    """Move cursor pointer to coordinates (x, y)."""

    x: int = Field(..., description="Horizontal pixel coordinate.")
    y: int = Field(..., description="Vertical pixel coordinate.")


class KeyAction(PCAction):
    """Keyboard key automation event."""

    key: str = Field(..., description="Key identifier (e.g. 'a', 'enter', 'ctrl').")
    action_type: str = "press"


class ShellAction(PCAction):
    """Local shell command execution."""

    command: str = Field(..., description="Terminal shell command string.")
    timeout: float = 10.0
    work_dir: Optional[str] = None


class ClipboardAction(PCAction):
    """System clipboard transfer interactions."""

    action: str = Field(..., description="Interactions: 'read', 'write'.")
    content: Optional[str] = None
