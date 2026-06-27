"""JARVIS OS - Browser Engine API Routing.

Exposes REST and WebSocket endpoints for external client automation integrations.
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from core.browser.client import JarvisBrowser
from core.browser.engine import BrowserEngine

router = APIRouter(prefix="/api/v1/browser", tags=["browser"])

# Temporary storage for active engine/client references
_global_engine: Optional[BrowserEngine] = None
_global_browser: Optional[JarvisBrowser] = None


def set_routing_context(engine: BrowserEngine, browser: JarvisBrowser) -> None:
    """Configure routing context references for endpoints."""
    global _global_engine, _global_browser
    _global_engine = engine
    _global_browser = browser


def get_browser() -> JarvisBrowser:
    """Dependency helper resolving active JarvisBrowser client."""
    print("get_browser CALLED, _global_browser is:", _global_browser)
    if not _global_browser:
        raise HTTPException(status_code=503, detail="Browser SDK is not initialized.")
    return _global_browser


def get_engine() -> BrowserEngine:
    """Dependency helper resolving active BrowserEngine coordinator."""
    print("get_engine CALLED, _global_engine is:", _global_engine)
    if not _global_engine:
        raise HTTPException(
            status_code=503, detail="Browser Engine is not initialized."
        )
    return _global_engine


class OpenTabRequest(BaseModel):
    """Payload to open and navigate a browser tab."""

    url: str


class NavigateRequest(BaseModel):
    """Payload to navigate active tab viewport."""

    url: str


class ClickRequest(BaseModel):
    """Payload to click selector target."""

    tab_id: str
    selector: str


@router.post("/open")
async def open_tab(
    req: OpenTabRequest, browser: JarvisBrowser = Depends(get_browser)
) -> Dict[str, Any]:
    """Open tab and register active URL."""
    try:
        tab_id = await browser.open_tab(req.url)
        return {"status": "SUCCESS", "tab_id": tab_id}
    except Exception as err:
        raise HTTPException(status_code=400, detail=str(err))


@router.post("/navigate")
async def navigate(
    req: NavigateRequest, engine: BrowserEngine = Depends(get_engine)
) -> Dict[str, Any]:
    """Navigate current viewport."""
    try:
        ok = await engine.navigate(req.url)
        return {"status": "SUCCESS" if ok else "ERROR"}
    except Exception as err:
        raise HTTPException(status_code=400, detail=str(err))


@router.post("/click")
async def click(
    req: ClickRequest, browser: JarvisBrowser = Depends(get_browser)
) -> Dict[str, Any]:
    """Simulate click instruction."""
    try:
        ok = await browser.click_element(req.tab_id, req.selector)
        return {"status": "SUCCESS" if ok else "ERROR"}
    except Exception as err:
        raise HTTPException(status_code=400, detail=str(err))


@router.get("/extract-dom")
async def extract_dom(engine: BrowserEngine = Depends(get_engine)) -> Dict[str, Any]:
    """Retrieve raw HTML string content."""
    try:
        dom = await engine.extract_dom()
        return {"status": "SUCCESS", "dom": dom}
    except Exception as err:
        raise HTTPException(status_code=400, detail=str(err))


ws_router = APIRouter(tags=["browser"])


@ws_router.websocket("/ws/v1/browser/viewport")
async def viewport_stream(
    websocket: WebSocket, engine: BrowserEngine = Depends(get_engine)
) -> None:
    """Stream base64 screenshot frame images over WebSocket."""
    await websocket.accept()
    try:
        while True:
            # Receive ping/request frame from client
            _ = await websocket.receive_text()
            # Fetch latest base64 screenshot data
            screenshot = await engine.driver.take_screenshot()
            await websocket.send_json({"frame": screenshot})
    except WebSocketDisconnect:
        pass
    except Exception:
        import traceback

        traceback.print_exc()
        await websocket.close()
