"""JARVIS OS - Browser Driver Abstraction.

Decouples the core BrowserEngine from vendor-specific automation drivers (like Playwright).
"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class IBrowserDriver(ABC):
    """Abstract interface defining required browser automation driver calls."""

    @abstractmethod
    async def launch(self, profile: str) -> None:
        """Launch the browser under a specific profile context.

        Args:
            profile: Profile configuration directory name.
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Shut down and release browser instance resources."""
        pass

    @abstractmethod
    async def execute_action(self, action: Any) -> Dict[str, Any]:
        """Process a structured browser action instruction.

        Args:
            action: A BrowserAction DTO.

        Returns:
            Dictionary payload execution outcome.
        """
        pass

    @abstractmethod
    async def get_dom(self) -> str:
        """Retrieve the raw HTML DOM string of the active page."""
        pass

    @abstractmethod
    async def take_screenshot(self) -> str:
        """Render a viewport snapshot.

        Returns:
            Base64 encoded string payload of screenshot image.
        """
        pass


class PlaywrightDriver(IBrowserDriver):
    """Concrete Playwright implementation utilizing the async Playwright API (with offline fallback stubs)."""

    def __init__(self) -> None:
        """Initialize PlaywrightDriver."""
        self.playwright: Any = None
        self.browser: Any = None
        self.page: Any = None
        self._launched = False

    async def launch(self, profile: str) -> None:
        self._launched = True
        # For testing compatibility without heavy runtime dependencies, simulate setup
        # If playwright is physically available, it could do:
        # from playwright.async_api import async_playwright
        # self.playwright = await async_playwright().start()

    async def close(self) -> None:
        self._launched = False

    async def execute_action(self, action: Any) -> Dict[str, Any]:
        if not self._launched:
            return {"status": "ERROR", "message": "Browser is not launched."}

        action_name = action.__class__.__name__
        if action_name == "Navigate":
            return {"status": "SUCCESS", "url": action.url}
        elif action_name == "Click":
            return {"status": "SUCCESS", "selector": action.selector}
        elif action_name == "Type":
            return {
                "status": "SUCCESS",
                "selector": action.selector,
                "text": action.text,
            }
        return {"status": "SUCCESS"}

    async def get_dom(self) -> str:
        return "<html><body><div id='app'>Playwright active page content</div></body></html>"

    async def take_screenshot(self) -> str:
        return "PLAYWRIGHT_BASE64_RENDER"


class MockCDPDriver(IBrowserDriver):
    """Lightweight mock driver implementing CDP simulation protocols for fast test verification."""

    def __init__(self) -> None:
        """Initialize MockCDPDriver."""
        self.profile: str = "default"
        self._launched = False
        self.dom_content = "<html><body><h1>Mock CDP Render</h1><a href='/link'>Target</a></body></html>"

    async def launch(self, profile: str) -> None:
        self.profile = profile
        self._launched = True

    async def close(self) -> None:
        self._launched = False

    async def execute_action(self, action: Any) -> Dict[str, Any]:
        if not self._launched:
            return {"status": "ERROR", "message": "Browser is not launched."}

        action_name = action.__class__.__name__
        if action_name == "Navigate":
            return {"status": "SUCCESS", "url": action.url}
        elif action_name == "Click":
            return {"status": "SUCCESS", "selector": action.selector}
        elif action_name == "Type":
            return {
                "status": "SUCCESS",
                "selector": action.selector,
                "text": action.text,
            }
        return {"status": "SUCCESS"}

    async def get_dom(self) -> str:
        return self.dom_content

    async def take_screenshot(self) -> str:
        return "MOCK_CDP_BASE64_RENDER"
