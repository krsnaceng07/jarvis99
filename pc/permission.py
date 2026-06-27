"""JARVIS OS - PC Permission Manager.

Validates action categories and security permission blocks prior to execution.
"""

from typing import Set

from core.exceptions import JarvisSystemError


class PCPermissionManager:
    """Restricts PC automation and executes security check verifications."""

    def __init__(self) -> None:
        """Initialize PCPermissionManager."""
        self.allowed_permissions: Set[str] = {
            "KEYBOARD",
            "MOUSE",
            "CLIPBOARD",
            "SCREENSHOT",
            "WINDOW_CONTROL",
            "FILESYSTEM",
            "SHELL",
        }

    def verify_permission(self, permission: str) -> None:
        """Verify the specified permission is active.

        Args:
            permission: Permission name code parameter.

        Raises:
            JarvisSystemError: If permission verification fails.
        """
        if permission not in self.allowed_permissions:
            raise JarvisSystemError(
                code="PERMISSION_001",
                message=f"PC Controller permission '{permission}' is denied.",
            )
