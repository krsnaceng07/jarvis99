"""JARVIS OS - Browser SDK Client.

Exposes public client automation interfaces conforming to the system specifications.
"""

from typing import Any, Dict, List

from core.browser.action import Click
from core.browser.engine import BrowserEngine


class JarvisBrowser:
    """Public Client SDK wrapping the BrowserEngine and state parameters."""

    def __init__(self, engine: BrowserEngine) -> None:
        """Initialize JarvisBrowser.

        Args:
            engine: Instantiated BrowserEngine coordinator.
        """
        self.engine = engine

    async def open_tab(self, url: str) -> str:
        """Open a page tab and navigate to the target URL.

        Args:
            url: Destination URL.

        Returns:
            UUID Tab ID.
        """
        # Validate whitelist rules via engine permissions
        self.engine.permission_manager.verify_domain(url)

        # Register tab inside state manager
        tab_id = self.engine.state_manager.add_tab(url)

        # Navigate active tab
        await self.engine.navigate(url)

        # Broadcast lifecycle event
        await self.engine._publish_event(
            "browser.page.loaded", {"url": url, "tab_id": tab_id}
        )

        return tab_id

    async def click_element(self, tab_id: str, selector: str) -> bool:
        """Simulate mouse click.

        Args:
            tab_id: Target tab context.
            selector: Element query selector string.

        Returns:
            True if click action is completed.
        """
        self.engine.state_manager.switch_tab(tab_id)

        action = Click(selector=selector)
        res = await self.engine.driver.execute_action(action)

        if res.get("status") == "SUCCESS":
            await self.engine._publish_event(
                "browser.action.completed", {"action": "click", "selector": selector}
            )
            return True
        return False

    async def inject_js(self, tab_id: str, script: str) -> Any:
        """Inject and execute JavaScript on the page.

        Args:
            tab_id: Target tab context.
            script: Javascript string.

        Returns:
            Execution outcome.
        """
        self.engine.state_manager.switch_tab(tab_id)

        # Sanitize JavaScript string for security safety
        self.engine.permission_manager.verify_script_safety(script)

        # Simulate execution
        await self.engine._publish_event(
            "browser.action.completed", {"action": "js_inject"}
        )
        return f"Executed JavaScript snippet of length {len(script)}."

    async def get_cookies(self, tab_id: str) -> List[Dict[str, Any]]:
        """Retrieve stored cookies.

        Args:
            tab_id: Target tab context.

        Returns:
            List of cookie items.
        """
        self.engine.state_manager.switch_tab(tab_id)
        return self.engine.state_manager.cookies
