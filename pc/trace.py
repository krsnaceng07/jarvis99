"""JARVIS OS - PC Action Telemetry Trace.

Registers details of completed keyboard, mouse, and shell commands for security audits.
"""

from datetime import datetime, timezone
from typing import Optional, Tuple

from pydantic import BaseModel, Field


class PCActionTrace(BaseModel):
    """Execution telemetry record mapping single PC automation steps."""

    session_id: str = Field(..., description="Active session UUID.")
    action_id: str = Field(..., description="Unique action step UUID.")
    action_type: str = Field(..., description="Action category (e.g. ClickAction).")
    duration_ms: int = Field(..., description="Time taken to execute in milliseconds.")
    success: bool = Field(..., description="Whether action finished without error.")
    retries: int = 0
    permission_result: str = "GRANTED"
    coordinates: Optional[Tuple[int, int]] = None
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Completion time marker.",
    )
