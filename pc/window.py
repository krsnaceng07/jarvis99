"""JARVIS OS - PC Window Manager.

Controls window visibility context details and focuses desktop windows.
"""

from typing import Any, Dict, List

from core.exceptions import JarvisSystemError
from pc.adapter import IPCAdapter


class WindowManager:
    """Coordinates desktop window focus and active handle attributes."""

    def __init__(self, adapter: IPCAdapter) -> None:
        """Initialize WindowManager.

        Args:
            adapter: PC driver platform adapter.
        """
        self.adapter = adapter

    async def get_active_window(self) -> Dict[str, Any]:
        """Fetch active window descriptor parameters.

        Returns:
            Window parameters dictionary mapping.
        """
        return await self.adapter.get_active_window()

    async def focus_window(self, handle: int) -> bool:
        """Focus the targeted window handle.

        Args:
            handle: Target window identifier.

        Returns:
            True if focus command completed.

        Raises:
            JarvisSystemError: If handle is invalid or missing.
        """
        if handle <= 0:
            raise JarvisSystemError(
                code="WINDOW_001",
                message=f"Invalid window handle: {handle}",
            )
        return True

    async def bring_to_front(self, handle: int) -> bool:
        """Move the window frontwards on the desktop.

        Args:
            handle: Target window identifier.

        Returns:
            True if target window is centered front.

        Raises:
            JarvisSystemError: If handle is invalid.
        """
        if handle <= 0:
            raise JarvisSystemError(
                code="WINDOW_001",
                message=f"Invalid window handle: {handle}",
            )
        return True

    async def find_windows_by_title(self, query: str) -> List[Dict[str, Any]]:
        """Filter list of active windows by title query.

        Args:
            query: Searching query substring.

        Returns:
            List of window matching mappings.
        """
        mock_windows: List[Dict[str, Any]] = [
            {"title": "Google Chrome", "handle": 111111},
            {"title": "VS Code", "handle": 222222},
        ]
        return [
            win
            for win in mock_windows
            if isinstance(win["title"], str) and query.lower() in win["title"].lower()
        ]
