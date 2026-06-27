"""JARVIS OS - PC Automation Session Context.

Maintains active session lifecycle states, histories, and rollback coordinates.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4


class PCSession:
    """Session variables tracking executed trace logs and recovery states."""

    def __init__(self, session_id: Optional[str] = None) -> None:
        """Initialize PCSession.

        Args:
            session_id: Optional UUID string override.
        """
        self.session_id = session_id or str(uuid4())
        self.started_at = datetime.now(timezone.utc)
        self.active_window: Optional[Dict[str, Any]] = None
        self.active_monitor: int = 0
        self.rollback_stack: List[Any] = []
        self.permission_snapshot: Dict[str, bool] = {}
        self.action_history: List[Any] = []

    def record_action(self, trace: Any) -> None:
        """Log a completed action trace to the history lists.

        Args:
            trace: Telemetry trace details.
        """
        self.action_history.append(trace)

    def push_rollback(self, action: Any) -> None:
        """Append a revert action to the rollback stack.

        Args:
            action: Rollback recovery action parameters.
        """
        self.rollback_stack.append(action)

    def pop_rollback(self) -> Optional[Any]:
        """Pop the last rollback action.

        Returns:
            Revert action or None.
        """
        if self.rollback_stack:
            return self.rollback_stack.pop()
        return None
