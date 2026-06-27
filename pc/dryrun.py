"""JARVIS OS - PC Controller DryRun Simulator.

Validates coordinate parameters and shell safeties without triggering actual OS interactions.
"""

from typing import Any, Dict

from core.exceptions import JarvisSystemError
from pc.display import DisplayManager
from pc.permission import PCPermissionManager


class DryRunExecutor:
    """Simulates validation pipelines for actions before dispatching them."""

    def __init__(
        self, permission_manager: PCPermissionManager, display_manager: DisplayManager
    ) -> None:
        """Initialize DryRunExecutor.

        Args:
            permission_manager: Active permission manager.
            display_manager: Active display manager.
        """
        self.permission_manager = permission_manager
        self.display_manager = display_manager

    async def validate_action(self, action: Any) -> Dict[str, Any]:
        """Verify command arguments, coordinates, and permissions.

        Args:
            action: PCAction DTO.

        Returns:
            Dictionary validation report.

        Raises:
            JarvisSystemError: If validation checks fail.
        """
        action_name = action.__class__.__name__

        # 1. Verify general permission boundaries
        if action_name in ("ClickAction", "MoveAction"):
            self.permission_manager.verify_permission("MOUSE")
            # Bounds check coordinates
            if not self.display_manager.is_within_bounds(action.x, action.y):
                raise JarvisSystemError(
                    code="DRYRUN_001",
                    message=f"Coordinates ({action.x}, {action.y}) are outside active monitor boundaries.",
                )

        elif action_name == "KeyAction":
            self.permission_manager.verify_permission("KEYBOARD")

        elif action_name == "ShellAction":
            self.permission_manager.verify_permission("SHELL")
            # Dry-run allowlist checks on command base
            cmd_base = (
                action.command.strip().split()[0].lower()
                if action.command.strip()
                else ""
            )
            allowed = ["dir", "ls", "echo", "pwd", "cd", "git"]
            if cmd_base not in allowed:
                raise JarvisSystemError(
                    code="DRYRUN_002",
                    message=f"DryRun Command verification failed: '{cmd_base}' is restricted.",
                )

        elif action_name == "ClipboardAction":
            self.permission_manager.verify_permission("CLIPBOARD")

        return {
            "dry_run": True,
            "action_type": action_name,
            "valid": True,
            "message": "Action parameters successfully validated.",
        }
