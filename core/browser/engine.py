"""JARVIS OS - Browser Engine Coordinator.

Maintains BrowserEngine automation execution steps and compiles structured BrowserSnapshot telemetry DTOs.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from pydantic import BaseModel, Field

from core.browser.action import Navigate
from core.browser.driver import IBrowserDriver
from core.browser.permission import BrowserPermissionManager
from core.browser.profile import BrowserContextManager, BrowserProfileManager
from core.browser.state import BrowserStateManager
from core.exceptions import JarvisSystemError
from core.interfaces import EventBusInterface, InterAgentMessage

logger = logging.getLogger("jarvis.core.browser.engine")


class BrowserSnapshot(BaseModel):
    """Telemetry data mapping the active page state viewport details."""

    url: str
    title: str
    dom: str
    text: str
    links: List[str] = Field(default_factory=list)
    forms: List[Dict[str, Any]] = Field(default_factory=list)
    tables: List[List[str]] = Field(default_factory=list)
    accessibility_tree: Dict[str, Any] = Field(default_factory=dict)
    screenshot: str = ""
    cookies_summary: List[Dict[str, Any]] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    page_metadata: Dict[str, Any] = Field(default_factory=dict)


class BrowserEngine:
    """Orchestrates page navigations, action execution, and DOM metrics compilation."""

    def __init__(
        self,
        driver: IBrowserDriver,
        state_manager: BrowserStateManager,
        permission_manager: BrowserPermissionManager,
        profile_manager: BrowserProfileManager,
        context_manager: BrowserContextManager,
        event_bus: EventBusInterface,
    ) -> None:
        """Initialize BrowserEngine.

        Args:
            driver: Browser automation driver instance.
            state_manager: System state manager.
            permission_manager: Permission security manager.
            profile_manager: Profile workspace manager.
            context_manager: Active context registry manager.
            event_bus: Core messaging bus interface.
        """
        self.driver = driver
        self.state_manager = state_manager
        self.permission_manager = permission_manager
        self.profile_manager = profile_manager
        self.context_manager = context_manager
        self.event_bus = event_bus

    async def navigate(self, url: str) -> bool:
        """Verify, navigate, and broadcast loaded events on success.

        Args:
            url: Target destination URL.

        Returns:
            True if navigation succeeded.

        Raises:
            JarvisSystemError: If permission or navigation fail.
        """
        # 1. Enforce permission gates
        self.permission_manager.verify_domain(url)

        # Broadcast start event
        await self._publish_event("browser.started", {"url": url})

        start_time = time.perf_counter()
        try:
            # 2. Trigger driver execute Navigate action
            action = Navigate(url=url)
            res = await self.driver.execute_action(action)
            duration_ms = int((time.perf_counter() - start_time) * 1000.0)

            if res.get("status") == "SUCCESS":
                self.state_manager.log_navigation(url)
                # Broadcast page loaded success event
                await self._publish_event(
                    "browser.page.loaded",
                    {"url": url, "duration_ms": duration_ms},
                )
                return True
            else:
                raise JarvisSystemError(
                    code="ENGINE_001",
                    message=f"Navigation failed: {res.get('message')}",
                )

        except Exception as err:
            await self._publish_event(
                "browser.page.failed", {"url": url, "error": str(err)}
            )
            raise err

    async def extract_dom(self) -> str:
        """Retrieve active page DOM.

        Returns:
            String HTML document.
        """
        return await self.driver.get_dom()

    async def compile_snapshot(self) -> BrowserSnapshot:
        """Assemble current page state variables into a structured DTO.

        Returns:
            BrowserSnapshot populated model.
        """
        dom = await self.driver.get_dom()
        screenshot = await self.driver.take_screenshot()

        # Simulated link and form parser extraction
        links = []
        if "href=" in dom:
            links = [url.split('"')[0] for url in dom.split('href="')[1:] if '"' in url]

        forms = []
        if "<form" in dom:
            forms = [{"action": "#", "method": "post"}]

        # Accessibility tree parser stub
        acc_tree = {"role": "RootWebArea", "name": "Document"}

        snapshot = BrowserSnapshot(
            url=self.state_manager.active_tab_id or "about:blank",
            title="Active Page Title",
            dom=dom,
            text="Clean inner text extracted from document body.",
            links=links,
            forms=forms,
            tables=[],
            accessibility_tree=acc_tree,
            screenshot=screenshot,
            cookies_summary=self.state_manager.cookies,
            page_metadata={
                "status_code": 200,
                "content_type": "text/html",
                "load_time_ms": 250,
                "page_language": "en",
            },
        )

        return snapshot

    async def _publish_event(self, topic: str, body: Dict[str, Any]) -> None:
        """Helper to dispatch lifecycle events to the global event bus."""
        msg = InterAgentMessage(
            sender="BrowserEngine",
            receiver="All",
            action=topic,
            body=body,
        )
        await self.event_bus.publish(topic, msg)
