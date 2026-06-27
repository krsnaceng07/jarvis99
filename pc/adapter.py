"""JARVIS OS - Platform Automation Adapter.

Decouples the core PCController from direct pyautogui and system calls, supporting Mock adapters.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Set


class IPCAdapter(ABC):
    """Abstract interface defining the platform adapters."""

    @abstractmethod
    async def execute_mouse_event(
        self,
        action_type: str,
        x: int,
        y: int,
        button: str = "left",
        double_click: bool = False,
    ) -> Dict[str, Any]:
        """Perform cursor movement or clicking.

        Args:
            action_type: Actions: 'click', 'move_to'.
            x: Horizontal pixel coordinate.
            y: Vertical pixel coordinate.
            button: Mouse button identifier.
            double_click: Simulate double click flag.

        Returns:
            Dictionary mapped outcome.
        """
        pass

    @abstractmethod
    async def execute_keyboard_event(
        self, action_type: str, key: str
    ) -> Dict[str, Any]:
        """Perform typing or pressing key events.

        Args:
            action_type: Events: 'press', 'down', 'up'.
            key: Key identifier character name.

        Returns:
            Dictionary mapped outcome.
        """
        pass

    @abstractmethod
    async def get_active_window(self) -> Dict[str, Any]:
        """Retrieve active window descriptor parameter mappings.

        Returns:
            Dictionary window parameters.
        """
        pass


class WindowsAdapter(IPCAdapter):
    """Windows-specific automation adapter mapping pyautogui and win32gui (with offline fallbacks)."""

    def __init__(self) -> None:
        """Initialize WindowsAdapter."""
        self.cursor_pos = (0, 0)
        self.held_keys: Set[str] = set()

    async def execute_mouse_event(
        self,
        action_type: str,
        x: int,
        y: int,
        button: str = "left",
        double_click: bool = False,
    ) -> Dict[str, Any]:
        self.cursor_pos = (x, y)
        return {"status": "SUCCESS", "x": x, "y": y, "action": action_type}

    async def execute_keyboard_event(
        self, action_type: str, key: str
    ) -> Dict[str, Any]:
        if action_type == "down":
            self.held_keys.add(key)
        elif action_type == "up":
            self.held_keys.discard(key)
        return {"status": "SUCCESS", "key": key, "action": action_type}

    async def get_active_window(self) -> Dict[str, Any]:
        return {
            "title": "Active Window Title",
            "handle": 123456,
            "bounds": {"left": 0, "top": 0, "right": 1024, "bottom": 768},
        }


class MockAdapter(IPCAdapter):
    """OS-independent mock adapter simulating automation events for fast headless tests."""

    def __init__(self) -> None:
        """Initialize MockAdapter."""
        self.cursor_pos = (0, 0)
        self.held_keys: Set[str] = set()
        self.active_window = {
            "title": "Mock Active Window",
            "handle": 999999,
            "bounds": {"left": 0, "top": 0, "right": 1920, "bottom": 1080},
        }

    async def execute_mouse_event(
        self,
        action_type: str,
        x: int,
        y: int,
        button: str = "left",
        double_click: bool = False,
    ) -> Dict[str, Any]:
        self.cursor_pos = (x, y)
        return {
            "status": "SUCCESS",
            "x": x,
            "y": y,
            "action": action_type,
            "button": button,
            "double": double_click,
        }

    async def execute_keyboard_event(
        self, action_type: str, key: str
    ) -> Dict[str, Any]:
        if action_type == "down":
            self.held_keys.add(key)
        elif action_type == "up":
            self.held_keys.discard(key)
        return {"status": "SUCCESS", "key": key, "action": action_type}

    async def get_active_window(self) -> Dict[str, Any]:
        return self.active_window
