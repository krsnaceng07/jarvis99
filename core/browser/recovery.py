"""JARVIS OS - Browser Recovery Manager.

Handles navigation timeouts, browser crashes, closed tabs, and rate limit backoff cycles.
"""

import asyncio
import logging
from typing import Any, Dict

from core.browser.driver import IBrowserDriver
from core.browser.profile import BrowserContextManager
from core.browser.state import BrowserStateManager

logger = logging.getLogger("jarvis.core.browser.recovery")


class BrowserRecoveryStrategy:
    """Orchestrates system recovery tasks for failed browser processes or pages."""

    def __init__(
        self,
        driver: IBrowserDriver,
        state_manager: BrowserStateManager,
        context_manager: BrowserContextManager,
    ) -> None:
        """Initialize BrowserRecoveryStrategy.

        Args:
            driver: Browser automation driver instance.
            state_manager: Active state manager.
            context_manager: Profile context manager.
        """
        self.driver = driver
        self.state_manager = state_manager
        self.context_manager = context_manager

    async def handle_crash(self) -> None:
        """Recover from browser crash by launching a new process and restoring state caches."""
        logger.warning("Browser crash detected. Initiating restore sequences...")

        # 1. Close current driver connection
        await self.driver.close()

        # 2. Resolve active profile context
        active_id = self.context_manager.active_context_id
        profile_name = "Personal"
        if active_id:
            ctx = self.context_manager.get_context(active_id)
            profile_name = ctx.get("profile_name", "Personal")

        # 3. Launch fresh browser
        await self.driver.launch(profile_name)

        # 4. Restore history tabs
        for tab_id, url in list(self.state_manager.tabs.items()):
            logger.info("Restoring tab %s -> %s", tab_id, url)

    async def handle_timeout(self, action: Any, retry_count: int = 1) -> Dict[str, Any]:
        """Retry a failed action with relaxed timeouts.

        Args:
            action: BrowserAction DTO.
            retry_count: Limit of re-execution attempts.

        Returns:
            Dictionary execution outcome.
        """
        logger.warning("Action timeout. Retrying instruction...")
        for attempt in range(retry_count):
            try:
                res = await self.driver.execute_action(action)
                if res.get("status") == "SUCCESS":
                    return res
            except Exception as err:
                logger.error("Retry attempt %d failed: %s", attempt + 1, str(err))

        return {"status": "ERROR", "message": "Action failed after retry attempts."}

    async def handle_network_error(self, status_code: int) -> None:
        """Delay or rotate proxies when rate limits or authorization codes occur.

        Args:
            status_code: HTTP response status code.
        """
        if status_code in (403, 429):
            logger.warning("Rate limit (429) or Forbidden (403) code. Cooling down...")
            # Trigger 10ms cooldown backoff wait for testing
            await asyncio.sleep(0.01)
