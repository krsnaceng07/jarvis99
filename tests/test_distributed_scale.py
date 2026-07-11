"""
PHASE: 35
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/97_PHASE_35_DISTRIBUTED_SCALE_SPECIFICATION.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_federation_manager, get_kernel, get_scale_manager
from api.middleware import register_exception_handlers
from api.routes.federation_scale import router as scale_router
from core.runtime.scale import ScaleManager
from core.security.vault import VaultManager
from core.tools.sandbox import ISandbox


class FakeSandbox(ISandbox):
    """Fake sandbox capturing runs and returning deterministic outcomes."""

    def __init__(self) -> None:
        self.runs: List[Dict[str, Any]] = []

    async def run(
        self,
        image: str,
        command: List[str],
        env: Optional[Dict[str, str]] = None,
        timeout: float = 30.0,
        network_access: bool = False,
    ) -> Dict[str, Any]:
        self.runs.append(
            {
                "image": image,
                "command": command,
                "env": env,
                "timeout": timeout,
                "network_access": network_access,
            }
        )
        # Simple execution model mock
        if "print('hello')" in command[-1] or "hello" in command[-1]:
            return {
                "stdout": "hello\n",
                "stderr": "",
                "exit_code": 0,
                "duration": 0.1,
                "memory_usage": 5,
                "cpu_usage": 0.05,
                "truncated": False,
            }
        elif "raise Exception" in command[-1] or "fail" in command[-1]:
            return {
                "stdout": "",
                "stderr": "RuntimeError: testing failure\n",
                "exit_code": 1,
                "duration": 0.1,
                "memory_usage": 5,
                "cpu_usage": 0.05,
                "truncated": False,
            }
        return {
            "stdout": "mock run success\n",
            "stderr": "",
            "exit_code": 0,
            "duration": 0.1,
            "memory_usage": 5,
            "cpu_usage": 0.05,
            "truncated": False,
        }


class MockOrchestrator:
    """Mock Orchestrator to capture and report active worker/queue stats."""

    def __init__(self, active_worker_tasks_count: int = 0, queue_size: int = 0) -> None:
        self.active_worker_tasks = [None] * active_worker_tasks_count
        self.queue = type("MockQueue", (), {"size": queue_size})()


class MockFederationManager:
    """Mock FederationManager serving registered peer records."""

    def __init__(self, node_id: str, peers: List[Dict[str, Any]]) -> None:
        self.node_id = node_id
        self._peers = peers

    async def list_peers(self) -> List[Dict[str, Any]]:
        return self._peers

    async def verify_signature(
        self,
        sender_node_id: str,
        signature: str,
        timestamp_str: str,
        body_bytes: bytes,
        key_id: str,
        created_at: str,
        message_id: str,
        nonce: str,
    ) -> bool:
        # Check if node is registered as a peer
        if (
            not any(p["node_id"] == sender_node_id for p in self._peers)
            and sender_node_id != "node_b"
        ):
            return False

        # Freshness Check (300 seconds window)
        try:
            req_time = datetime.fromisoformat(timestamp_str)
            now_time = datetime.now(timezone.utc)
            if abs((now_time - req_time).total_seconds()) > 300.0:
                return False
        except Exception:
            return False

        # In testing we accept "sig_ok" directly or verify using a fixed string
        if signature == "sig_invalid":
            return False
        return True


class MockSettings:
    pass


@pytest.fixture
def scale_test_setup(monkeypatch: Any) -> Any:
    vault = VaultManager(key_path="secrets/fake_key", secrets_path="secrets/fake_vault")
    # Stub get_secret directly
    monkeypatch.setattr(
        vault,
        "get_secret",
        lambda name: "super_secret_p2p_key" if name == "federation_secret" else "",
    )

    peers = [
        {"node_id": "node_b", "base_url": "http://node-b.local"},
        {"node_id": "node_c", "base_url": "http://node-c.local"},
    ]
    fed_mgr = MockFederationManager("node_a", peers)
    orch = MockOrchestrator(active_worker_tasks_count=1, queue_size=2)
    sandbox = FakeSandbox()
    settings = MockSettings()

    scale_mgr = ScaleManager(
        settings=settings,
        db_manager=None,
        federation_manager=fed_mgr,
        vault_manager=vault,
        local_orchestrator=orch,
        local_sandbox=sandbox,
    )
    return scale_mgr, fed_mgr, orch, sandbox, vault


@pytest.mark.asyncio
async def test_scale_load_metrics_calculation(scale_test_setup: Any) -> None:
    """Verify local load factors calculation fetches accurate metrics."""
    scale_mgr, _, _, _, _ = scale_test_setup
    metrics = await scale_mgr.get_node_load_metrics()
    assert "cpu_usage" in metrics
    assert "memory_usage" in metrics
    # LocalOrchestrator active tasks count = 1 worker + 2 queue size = 3
    assert metrics["active_tasks"] == 3


@pytest.mark.asyncio
async def test_deterministic_lowest_load_selection(
    scale_test_setup: Any, monkeypatch: Any
) -> None:
    """Verify ScaleManager selects the peer carrying the lowest load deterministically."""
    scale_mgr, _, _, _, _ = scale_test_setup

    # Mock the REST query response metrics for peer nodes
    # Node B metrics: active_tasks=2
    # Node C metrics: active_tasks=1 (Lowest load)
    async def mock_fetch_peer_load_metrics(peer_node_id: str) -> Dict[str, Any]:
        if peer_node_id == "node_b":
            return {"active_tasks": 2, "cpu_usage": 0.2, "memory_usage": 0.2}
        elif peer_node_id == "node_c":
            return {"active_tasks": 1, "cpu_usage": 0.1, "memory_usage": 0.1}
        return {"active_tasks": 99, "cpu_usage": 0.9, "memory_usage": 0.9}

    monkeypatch.setattr(
        scale_mgr, "fetch_peer_load_metrics", mock_fetch_peer_load_metrics
    )

    best_peer = await scale_mgr.select_best_peer()
    assert best_peer == "node_c"  # lowest active tasks


@pytest.mark.asyncio
async def test_lowest_load_tie_breaking(
    scale_test_setup: Any, monkeypatch: Any
) -> None:
    """Verify lowest-load ties are resolved alphabetically by node_id."""
    scale_mgr, _, _, _, _ = scale_test_setup

    # Both node_b and node_c report identical loads
    async def mock_fetch_peer_load_metrics(peer_node_id: str) -> Dict[str, Any]:
        return {"active_tasks": 2, "cpu_usage": 0.2, "memory_usage": 0.2}

    monkeypatch.setattr(
        scale_mgr, "fetch_peer_load_metrics", mock_fetch_peer_load_metrics
    )

    best_peer = await scale_mgr.select_best_peer()
    # Alphabetically "node_b" < "node_c"
    assert best_peer == "node_b"


@pytest.mark.asyncio
async def test_load_metrics_caching_ttl(
    scale_test_setup: Any, monkeypatch: Any
) -> None:
    """Verify metrics caching respects the 2-3s TTL window."""
    scale_mgr, _, _, _, _ = scale_test_setup

    query_count = 0

    async def mock_get(*args: Any, **kwargs: Any) -> Any:
        nonlocal query_count
        query_count += 1
        return type(
            "Resp",
            (),
            {
                "status_code": 200,
                "json": lambda *a, **k: {
                    "active_tasks": 1,
                    "cpu_usage": 0.1,
                    "memory_usage": 0.1,
                },
            },
        )()

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    # First request: triggers API fetch
    metrics1 = await scale_mgr.fetch_peer_load_metrics("node_b")
    assert query_count == 1
    assert metrics1["active_tasks"] == 1

    # Second request: served from cache immediately
    metrics2 = await scale_mgr.fetch_peer_load_metrics("node_b")
    assert query_count == 1  # query_count stays 1

    # Invalidate cache by forcing expiration timestamp back
    scale_mgr._metrics_cache["node_b"] = (time.monotonic() - 5.0, metrics2)

    # Third request: cache expired, queries API again
    await scale_mgr.fetch_peer_load_metrics("node_b")
    assert query_count == 2


@pytest.mark.asyncio
async def test_run_offloaded_task_background(
    scale_test_setup: Any, monkeypatch: Any
) -> None:
    """Verify offloaded python tasks run inside sandbox and execute callback."""
    scale_mgr, _, _, sandbox, _ = scale_test_setup

    callback_posted = False
    callback_body = {}

    # Mock HTTP callback destination POST
    async def mock_post(*args: Any, **kwargs: Any) -> Any:
        nonlocal callback_posted, callback_body
        callback_posted = True
        content = kwargs.get("content") or args[2]
        callback_body = json.loads(content)
        return type("Resp", (), {"status_code": 200})()

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    task_id = "test-task-123"
    code = "print('hello')"

    await scale_mgr.run_offloaded_task_background(
        task_id=task_id, code=code, sender_node_id="node_b"
    )

    # Verify captured sandbox run
    assert len(sandbox.runs) == 1
    assert sandbox.runs[0]["image"] == "python:3.12-slim"
    assert "print('hello')" in sandbox.runs[0]["command"][-1]

    # Verify updated status
    assert scale_mgr._offloaded_tasks[task_id]["status"] == "SUCCESS"
    assert "hello\n" in scale_mgr._offloaded_tasks[task_id]["stdout"]

    # Verify callback triggered back to node_b
    assert callback_posted is True
    assert callback_body["task_id"] == task_id
    assert callback_body["status"] == "SUCCESS"
    assert callback_body["stdout"] == "hello\n"


def test_scale_api_endpoints_integration(scale_test_setup: Any) -> None:
    """Verify HTTP router handles signatures, task queueing, tool whitelists, and status queries."""
    scale_mgr, fed_mgr, _, sandbox, _ = scale_test_setup

    app = FastAPI()
    app.include_router(scale_router, prefix="/api/v1")
    register_exception_handlers(app)

    app.dependency_overrides[get_scale_manager] = lambda: scale_mgr
    app.dependency_overrides[get_federation_manager] = lambda: fed_mgr
    # Override get_kernel as well to prevent missing dependencies errors
    app.dependency_overrides[get_kernel] = lambda: type(
        "FakeKernel", (), {"container": None}
    )()

    client = TestClient(app)

    # 1. Unsigned requests fail signature middleware checks
    res_unsigned = client.get("/api/v1/federation/load")
    assert res_unsigned.status_code == 401

    # 2. Signed metrics query load success
    timestamp_str = datetime.now(timezone.utc).isoformat()
    message_id = str(uuid4())
    nonce = f"nonce_{uuid4().hex}"
    key_id = "fed_key_1"
    created_at = "2026-07-05T00:00:00Z"

    # Compute valid mock signature
    string_to_sign = (
        f"1:{message_id}:node_b:{timestamp_str}:{nonce}:{key_id}:{created_at}:"
    )
    sig = hmac.new(
        b"super_secret_p2p_key", string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    headers = {
        "X-Jarvis-Node-Id": "node_b",
        "X-Jarvis-Signature": sig,
        "X-Jarvis-Timestamp": timestamp_str,
        "X-Jarvis-Key-Id": key_id,
        "X-Jarvis-Created-At": created_at,
        "X-Jarvis-Message-Id": message_id,
        "X-Jarvis-Nonce": nonce,
    }

    res_signed = client.get("/api/v1/federation/load", headers=headers)
    assert res_signed.status_code == 200
    assert "cpu_usage" in res_signed.json()["data"]

    # 3. Offload queue task returns QUEUED status
    task_payload = {
        "task_id": "task-uuid-abc",
        "type": "execute_code",
        "payload": {
            "code": "print('hello')",
            "callback_url": "http://localhost/callback",
        },
    }
    payload_str = json.dumps(task_payload)
    string_to_sign_offload = f"1:{message_id}:node_b:{timestamp_str}:{nonce}:{key_id}:{created_at}:{payload_str}"
    sig_offload = hmac.new(
        b"super_secret_p2p_key", string_to_sign_offload.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    headers["X-Jarvis-Signature"] = sig_offload

    res_offload = client.post(
        "/api/v1/federation/offload", json=task_payload, headers=headers
    )
    assert res_offload.status_code == 200
    assert res_offload.json()["data"]["status"] == "QUEUED"

    # 4. Remote tool execution boundary (whitelisted python_sandbox succeeds)
    tool_payload = {
        "tool_name": "python_sandbox",
        "arguments": {"code": "print('hello')"},
    }
    tool_str = json.dumps(tool_payload)
    string_to_sign_tool = f"1:{message_id}:node_b:{timestamp_str}:{nonce}:{key_id}:{created_at}:{tool_str}"
    sig_tool = hmac.new(
        b"super_secret_p2p_key", string_to_sign_tool.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    headers["X-Jarvis-Signature"] = sig_tool

    res_tool = client.post(
        "/api/v1/federation/tools/execute", json=tool_payload, headers=headers
    )
    assert res_tool.status_code == 200
    assert res_tool.json()["data"]["success"] is True

    # 5. Remote tool execution boundary (non-whitelisted shell_runtime fails)
    unauthorized_payload = {
        "tool_name": "shell_runtime",
        "arguments": {"cmd": "rm -rf /"},
    }
    unauth_str = json.dumps(unauthorized_payload)
    string_to_sign_unauth = f"1:{message_id}:node_b:{timestamp_str}:{nonce}:{key_id}:{created_at}:{unauth_str}"
    sig_unauth = hmac.new(
        b"super_secret_p2p_key", string_to_sign_unauth.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    headers["X-Jarvis-Signature"] = sig_unauth

    res_unauth = client.post(
        "/api/v1/federation/tools/execute", json=unauthorized_payload, headers=headers
    )
    assert res_unauth.status_code == 403
    assert "forbidden" in res_unauth.json()["error"]["message"]
