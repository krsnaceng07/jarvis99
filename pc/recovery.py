"""JARVIS OS - PC Automation Recovery Manager.

Handles rollbacks, cleanup resets, clipboard restorations, and held keyboard key releases.
"""

import logging
from typing import Set

from pc.adapter import IPCAdapter
from pc.session import PCSession

logger = logging.getLogger("jarvis.pc.recovery")


class AutomationRecoveryManager:
    """Manages automation recovery flows, key releases, and clipboard rollbacks."""

    def __init__(self, adapter: IPCAdapter) -> None:
        """Initialize AutomationRecoveryManager.

        Args:
            adapter: Platform automation adapter.
        """
        self.adapter = adapter
        self.clipboard_backup: str = ""

    def backup_clipboard(self, content: str) -> None:
        """Backup current clipboard text before writing.

        Args:
            content: Clipboard backup data string.
        """
        self.clipboard_backup = content

    async def restore_clipboard(self) -> None:
        """Restore clipboard back to backed-up content."""
        logger.info("Restoring clipboard state to: %s", self.clipboard_backup)
        # Dummy clipboard adapter set
        pass

    async def release_keys(self, held_keys: Set[str]) -> None:
        """Release all held down keyboard keys.

        Args:
            held_keys: Set of active held down keys.
        """
        for key in list(held_keys):
            logger.info("Releasing stuck held key: %s", key)
            await self.adapter.execute_keyboard_event("up", key)

    async def rollback(self, session: PCSession) -> None:
        """Pop and execute revert actions from session rollback stack.

        Args:
            session: Target active PCSession.
        """
        logger.warning("Initiating rollback for session: %s", session.session_id)
        while True:
            action = session.pop_rollback()
            if not action:
                break

            action_name = action.__class__.__name__
            try:
                if action_name == "MoveAction":
                    # Move mouse back to original location
                    await self.adapter.execute_mouse_event(
                        "move_to", action.x, action.y
                    )
                elif action_name == "ClipboardAction":
                    await self.restore_clipboard()
            except Exception as err:
                logger.error("Failed to execute rollback action: %s", str(err))
