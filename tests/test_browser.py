"""JARVIS OS - Browser Engine Unit and Integration Tests.

Validates drivers, state histories, permission gates, action models, DOM snapshots, recovery strategies, and API gateways.
"""

import asyncio
from typing import Any, Dict, List

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.browser.action import Click, Navigate, Type
from core.browser.client import JarvisBrowser
from core.browser.driver import MockCDPDriver
from core.browser.engine import BrowserEngine, BrowserSnapshot
from core.browser.permission import BrowserPermissionManager
from core.browser.profile import BrowserContextManager, BrowserProfileManager
from core.browser.recovery import BrowserRecoveryStrategy
from core.browser.routes import router, set_routing_context, ws_router
from core.browser.state import BrowserStateManager
from core.exceptions import JarvisSystemError
from core.interfaces import EventBusInterface, InterAgentMessage


class MockEventBus(EventBusInterface):
    """Mock event bus for capturing published messages."""

    def __init__(self) -> None:
        """Initialize MockEventBus."""
        self.published_events: List[Dict[str, Any]] = []

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    async def publish(self, topic: str, message: InterAgentMessage) -> bool:
        self.published_events.append({"topic": topic, "message": message})
        return True

    async def subscribe(self, topic: str, callback: Any) -> str:
        return "mock_sub_id"


@pytest.fixture
def browser_setup() -> Dict[str, Any]:
    """Helper fixture initializing the browser component dependencies."""
    driver = MockCDPDriver()
    state_manager = BrowserStateManager()
    permission_manager = BrowserPermissionManager()
    profile_manager = BrowserProfileManager()
    context_manager = BrowserContextManager(profile_manager)
    event_bus = MockEventBus()

    engine = BrowserEngine(
        driver=driver,
        state_manager=state_manager,
        permission_manager=permission_manager,
        profile_manager=profile_manager,
        context_manager=context_manager,
        event_bus=event_bus,
    )

    client = JarvisBrowser(engine)
    recovery = BrowserRecoveryStrategy(
        driver=driver,
        state_manager=state_manager,
        context_manager=context_manager,
    )

    return {
        "driver": driver,
        "state_manager": state_manager,
        "permission_manager": permission_manager,
        "profile_manager": profile_manager,
        "context_manager": context_manager,
        "event_bus": event_bus,
        "engine": engine,
        "client": client,
        "recovery": recovery,
    }


@pytest.mark.asyncio
async def test_dynamic_sdk_import() -> None:
    """Verify that jarvis.sdk.* namespaces are importable from sys.modules."""
    # Ensure namespaces are loaded by loading the kernel module first
    import jarvis.sdk.browser
    import jarvis.sdk.skills

    import core.kernel  # noqa: F401

    assert jarvis.sdk.skills.JarvisSkill is not None
    assert jarvis.sdk.browser.JarvisBrowser is not None


@pytest.mark.asyncio
async def test_driver_launch_close(browser_setup: Dict[str, Any]) -> None:
    """Verify driver process launches and closes."""
    driver = browser_setup["driver"]
    assert not driver._launched

    await driver.launch("Work")
    assert driver._launched
    assert driver.profile == "Work"

    await driver.close()
    assert not driver._launched


@pytest.mark.asyncio
async def test_profiles_and_contexts(browser_setup: Dict[str, Any]) -> None:
    """Verify profile isolation and context switching rules."""
    pm = browser_setup["profile_manager"]
    cm = browser_setup["context_manager"]

    # Profile directories resolution
    path = pm.get_profile_path("Personal")
    assert "personal" in path

    with pytest.raises(JarvisSystemError):
        pm.get_profile_path("InvalidProfile")

    # Isolated Contexts Creation
    ctx1 = cm.create_context("Personal")
    ctx2 = cm.create_context("Work")

    assert ctx1 != ctx2
    assert cm.active_context_id == ctx1

    cm.switch_context(ctx2)
    assert cm.active_context_id == ctx2

    cm.close_context(ctx1)
    with pytest.raises(JarvisSystemError):
        cm.get_context(ctx1)


@pytest.mark.asyncio
async def test_state_management(browser_setup: Dict[str, Any]) -> None:
    """Verify tab allocations and navigation tracking logs."""
    sm = browser_setup["state_manager"]

    tab1 = sm.add_tab("https://python.org")
    tab2 = sm.add_tab("https://google.com")

    assert len(sm.tabs) == 2
    assert sm.active_tab_id == tab2

    sm.switch_tab(tab1)
    assert sm.active_tab_id == tab1

    sm.add_cookie("session", "xyz", "google.com")
    assert len(sm.cookies) == 1
    assert sm.cookies[0]["name"] == "session"


@pytest.mark.asyncio
async def test_permission_gates(browser_setup: Dict[str, Any]) -> None:
    """Verify download, script injection, and whitelist destination checks."""
    pm = browser_setup["permission_manager"]

    # Whitelist domain verification
    pm.verify_domain("https://google.com/search")
    pm.verify_domain("http://localhost:8000")

    with pytest.raises(JarvisSystemError) as exc:
        pm.verify_domain("https://malicious-website.com")
    assert "restricted" in exc.value.message

    # Executable downloads block
    with pytest.raises(JarvisSystemError) as exc:
        pm.verify_domain("https://google.com/malicious.exe")
    assert "blocked" in exc.value.message

    # JavaScript safety checks
    pm.verify_script_safety("console.log('Safe script');")

    with pytest.raises(JarvisSystemError) as exc:
        pm.verify_script_safety("const proc = require('child_process');")
    assert "rejected" in exc.value.message


@pytest.mark.asyncio
async def test_action_model_and_engine(browser_setup: Dict[str, Any]) -> None:
    """Verify navigations, action execution, and snapshot compilations."""
    engine = browser_setup["engine"]
    driver = browser_setup["driver"]
    event_bus = browser_setup["event_bus"]

    # Launch driver
    await driver.launch("Testing")

    # Navigate
    ok = await engine.navigate("https://google.com")
    assert ok
    assert len(event_bus.published_events) == 2
    assert event_bus.published_events[0]["topic"] == "browser.started"
    assert event_bus.published_events[1]["topic"] == "browser.page.loaded"

    # Compile Telemetry Snapshot
    snap = await engine.compile_snapshot()
    assert isinstance(snap, BrowserSnapshot)
    assert snap.page_metadata["status_code"] == 200
    assert "html" in snap.dom.lower()


@pytest.mark.asyncio
async def test_recovery_strategy(browser_setup: Dict[str, Any]) -> None:
    """Verify timeout and crash recovery operations."""
    recovery = browser_setup["recovery"]
    driver = browser_setup["driver"]
    sm = browser_setup["state_manager"]

    # Crash recovery
    await driver.launch("Testing")
    sm.add_tab("https://google.com")
    assert driver._launched

    await recovery.handle_crash()
    assert driver._launched  # Re-launched automatically

    # Timeout recovery retry
    action = Type(selector="#search", text="JARVIS")
    res = await recovery.handle_timeout(action, retry_count=2)
    assert res["status"] == "SUCCESS"

    # Network error rate-limiting backoff
    await recovery.handle_network_error(429)


def test_api_routes(browser_setup: Dict[str, Any]) -> None:
    """Verify REST API and WebSocket controller endpoints."""
    engine = browser_setup["engine"]
    client_sdk = browser_setup["client"]

    # Configure active context references
    set_routing_context(engine, client_sdk)

    # Boot mock drivers
    asyncio.run(engine.driver.launch("Testing"))
    engine.state_manager.add_tab("https://google.com")

    # Run TestClient
    app = FastAPI()
    app.include_router(router)
    app.include_router(ws_router)
    client = TestClient(app)

    # Open Tab
    res = client.post("/api/v1/browser/open", json={"url": "https://google.com"})
    assert res.status_code == 200
    assert "tab_id" in res.json()

    # Navigate
    res = client.post("/api/v1/browser/navigate", json={"url": "https://google.com"})
    assert res.status_code == 200

    # Extract DOM
    res = client.get("/api/v1/browser/extract-dom")
    assert res.status_code == 200
    assert "dom" in res.json()

    # WebSocket Viewport Stream
    with client.websocket_connect("/ws/v1/browser/viewport") as ws:
        ws.send_text("PING")
        frame = ws.receive_json()
        assert "frame" in frame


@pytest.mark.asyncio
async def test_playwright_driver_simulation() -> None:
    """Verify PlaywrightDriver simulation actions and states."""
    from core.browser.driver import PlaywrightDriver

    driver = PlaywrightDriver()
    await driver.launch("Personal")
    assert driver._launched

    # Navigate
    res = await driver.execute_action(Navigate(url="https://google.com"))
    assert res["status"] == "SUCCESS"

    # Click
    res = await driver.execute_action(Click(selector="div"))
    assert res["status"] == "SUCCESS"

    # Type
    res = await driver.execute_action(Type(selector="input", text="test"))
    assert res["status"] == "SUCCESS"

    # DOM & Screenshot
    dom = await driver.get_dom()
    assert "Playwright" in dom
    ss = await driver.take_screenshot()
    assert ss == "PLAYWRIGHT_BASE64_RENDER"

    # Unlaunched execute
    await driver.close()
    assert not driver._launched
    res = await driver.execute_action(Click(selector="div"))
    assert res["status"] == "ERROR"


@pytest.mark.asyncio
async def test_client_extra_actions(browser_setup: Dict[str, Any]) -> None:
    """Verify click, js injection, cookies get actions on JarvisBrowser."""
    client = browser_setup["client"]
    driver = browser_setup["driver"]
    state_manager = browser_setup["state_manager"]

    await driver.launch("Testing")
    tab_id = await client.open_tab("https://google.com")

    # Click
    ok = await client.click_element(tab_id, "button")
    assert ok

    # Injected Script
    res = await client.inject_js(tab_id, "console.log('hi');")
    assert "Executed" in res

    # Cookies
    state_manager.add_cookie("auth", "cookie_val", "google.com")
    cookies = await client.get_cookies(tab_id)
    assert len(cookies) == 1
    assert cookies[0]["name"] == "auth"


@pytest.mark.asyncio
async def test_state_manager_exceptions(browser_setup: Dict[str, Any]) -> None:
    """Verify exception raising for invalid states inside BrowserStateManager."""
    sm = browser_setup["state_manager"]

    with pytest.raises(JarvisSystemError):
        sm.close_tab("non_existent_tab")

    with pytest.raises(JarvisSystemError):
        sm.switch_tab("non_existent_tab")


@pytest.mark.asyncio
async def test_engine_navigation_failures(browser_setup: Dict[str, Any]) -> None:
    """Verify navigation crash triggers browser.page.failed events."""
    engine = browser_setup["engine"]
    driver = browser_setup["driver"]

    # Simulating driver failure
    await driver.launch("Testing")

    class FailingDriver(MockCDPDriver):
        async def execute_action(self, action: Any) -> Dict[str, Any]:
            return {"status": "FAIL", "message": "Simulated connection timeout error"}

    engine.driver = FailingDriver()

    with pytest.raises(JarvisSystemError) as exc:
        await engine.navigate("https://google.com")
    assert "Navigation failed" in exc.value.message


@pytest.mark.asyncio
async def test_recovery_edge_cases(browser_setup: Dict[str, Any]) -> None:
    """Verify recovery retry failures."""
    recovery = browser_setup["recovery"]

    # Timeout failures
    class TimeoutDriver(MockCDPDriver):
        async def execute_action(self, action: Any) -> Dict[str, Any]:
            raise TimeoutError("Timeout")

    recovery.driver = TimeoutDriver()
    action = Click(selector="div")
    res = await recovery.handle_timeout(action, retry_count=1)
    assert res["status"] == "ERROR"


def test_api_routes_errors(browser_setup: Dict[str, Any]) -> None:
    """Verify HTTP error code paths in API router."""
    # Context without initialization
    set_routing_context(None, None)  # type: ignore

    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    res = client.post("/api/v1/browser/open", json={"url": "https://google.com"})
    assert res.status_code == 503

    res = client.post("/api/v1/browser/navigate", json={"url": "https://google.com"})
    assert res.status_code == 503


@pytest.mark.asyncio
async def test_permission_denied(browser_setup: Dict[str, Any]) -> None:
    """Verify verify_action_permission raises error for denied permissions."""
    pm = browser_setup["permission_manager"]
    with pytest.raises(JarvisSystemError) as exc:
        pm.verify_action_permission("CAMERA")
    assert "denied" in exc.value.message


@pytest.mark.asyncio
async def test_context_manager_fallbacks(browser_setup: Dict[str, Any]) -> None:
    """Verify context manager fallback logic on active context deletion."""
    cm = browser_setup["context_manager"]

    # Close/Switch checks on invalid IDs
    with pytest.raises(JarvisSystemError):
        cm.close_context("invalid_id")

    with pytest.raises(JarvisSystemError):
        cm.switch_context("invalid_id")

    # Fallback check
    c1 = cm.create_context("Personal")
    c2 = cm.create_context("Work")
    cm.switch_context(c1)
    assert cm.active_context_id == c1

    cm.close_context(c1)
    assert cm.active_context_id == c2


def test_api_routes_exceptions(browser_setup: Dict[str, Any]) -> None:
    """Verify route error responses (400) when exceptions are raised in controllers."""
    engine = browser_setup["engine"]
    client_sdk = browser_setup["client"]

    set_routing_context(engine, client_sdk)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    # Trigger verify_domain validation error on open
    res = client.post("/api/v1/browser/open", json={"url": "https://malicious.com"})
    assert res.status_code == 400

    # Trigger navigation failure
    class CrashDriver(MockCDPDriver):
        async def execute_action(self, action: Any) -> Dict[str, Any]:
            return {"status": "FAIL", "message": "Failed"}

    engine.driver = CrashDriver()
    res = client.post("/api/v1/browser/navigate", json={"url": "https://google.com"})
    assert res.status_code == 400

    # Trigger click failure
    res = client.post(
        "/api/v1/browser/click", json={"tab_id": "invalid", "selector": "div"}
    )
    assert res.status_code == 400

    # Trigger extract-dom error
    class ErrorDOMDriver(MockCDPDriver):
        async def get_dom(self) -> str:
            raise ValueError("Failed DOM")

    engine.driver = ErrorDOMDriver()
    res = client.get("/api/v1/browser/extract-dom")
    assert res.status_code == 400
