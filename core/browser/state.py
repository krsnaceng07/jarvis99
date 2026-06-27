"""JARVIS OS - Browser State Manager.

Tracks tabs registry, focused targets, histories, and viewport configurations.
"""

from typing import Any, Dict, List, Optional
from uuid import uuid4

from core.exceptions import JarvisSystemError


class BrowserStateManager:
    """Maintains active browser windows, tab coordinates, cookie sets, and histories."""

    def __init__(self) -> None:
        """Initialize BrowserStateManager."""
        self.tabs: Dict[str, str] = {}
        self.active_tab_id: Optional[str] = None
        self.windows: List[Dict[str, Any]] = []
        self.cookies: List[Dict[str, Any]] = []
        self.downloads: List[Dict[str, Any]] = []
        self.history: List[str] = []
        self.viewport: Dict[str, Any] = {"width": 1280, "height": 720, "scale": 1.0}
        self.focused_element: Optional[str] = None

    def add_tab(self, url: str) -> str:
        """Register a new tab and assign focus.

        Args:
            url: Initial navigation URL.

        Returns:
            Tab ID UUID string.
        """
        tab_id = str(uuid4())
        self.tabs[tab_id] = url
        self.active_tab_id = tab_id
        self.log_navigation(url)
        return tab_id

    def close_tab(self, tab_id: str) -> None:
        """Remove a tab entry.

        Args:
            tab_id: Target tab ID.

        Raises:
            JarvisSystemError: If tab ID does not exist.
        """
        if tab_id not in self.tabs:
            raise JarvisSystemError(
                code="STATE_001",
                message=f"Tab ID '{tab_id}' is not registered.",
            )
        del self.tabs[tab_id]
        if self.active_tab_id == tab_id:
            self.active_tab_id = next(iter(self.tabs.keys())) if self.tabs else None

    def switch_tab(self, tab_id: str) -> None:
        """Switch focus to the selected tab.

        Args:
            tab_id: Target tab ID.

        Raises:
            JarvisSystemError: If tab ID does not exist.
        """
        if tab_id not in self.tabs:
            raise JarvisSystemError(
                code="STATE_001",
                message=f"Tab ID '{tab_id}' is not registered.",
            )
        self.active_tab_id = tab_id

    def log_navigation(self, url: str) -> None:
        """Append target URL to history stack.

        Args:
            url: Navigation target.
        """
        self.history.append(url)

    def add_cookie(self, name: str, value: str, domain: str) -> None:
        """Add a cookie item.

        Args:
            name: Cookie name.
            value: Cookie value.
            domain: Target scope domain.
        """
        self.cookies.append({"name": name, "value": value, "domain": domain})
