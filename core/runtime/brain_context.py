"""
PHASE: 37
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/99_PHASE_37_BRAIN_KERNEL_SPECIFICATION.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from typing import Any, Dict


class BrainContext:
    """Aggregates and tracks global variables, environmental inputs, and shared context."""

    def __init__(self) -> None:
        self._variables: Dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a variable from the global context."""
        return self._variables.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Store/update a variable in the global context."""
        self._variables[key] = value

    def clear(self) -> None:
        """Flush the context storage."""
        self._variables.clear()

    def export(self) -> Dict[str, Any]:
        """Export raw context snapshot dictionary."""
        return dict(self._variables)
