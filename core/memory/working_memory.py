"""
PHASE: 38
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/100_PHASE_38_UNIFIED_MEMORY_SPECIFICATION.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from typing import Any, Dict


class WorkingMemory:
    """Manages volatile context windows, transient goals, and immediate task parameters."""

    def __init__(self) -> None:
        self._data: Dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        """Get transient memory value."""
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set transient memory value."""
        self._data[key] = value

    def clear(self) -> None:
        """Flush working memory."""
        self._data.clear()

    def export(self) -> Dict[str, Any]:
        """Export transient snapshot."""
        return dict(self._data)
