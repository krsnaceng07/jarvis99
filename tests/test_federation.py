"""
PHASE: 31
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/93_PHASE_31_FEDERATION_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/fa98328c-ff31-452a-9668-808df53aa5a3/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import asyncio
import contextlib
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_federation_manager, get_kernel
from api.middleware import register_exception_handlers
from api.routes.federation import router as federation_router
from core.interfaces import EventBusInterface, InterAgentMessage
from core.runtime.federation import FederationManager
from core.security.auth_context import RequestContext, active_context
from core.security.vault import VaultManager


class FakeEventBus(EventBusInterface):
    """Fake Event Bus to capture published federation audit events."""

    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    async def initialize(self) -> None:
        pass

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def shutdown(self) -> None:
        pass

    async def publish(self, topic: str, message: InterAgentMessage) -> bool:
        self.events.append({"topic": topic, "message": message})
        return True

    async def subscribe(self, topic: str, callback: Any) -> str:
        return "sub"

    async def unsubscribe(self, topic: str, callback: Any) -> None:
        pass


class MockSettings:
    """Mock Settings containing federation properties."""

    class FederationCfg:
        def __init__(self, node_id: str, peers_path: str) -> None:
            self.enabled = True
            self.node_id = node_id
            self.peers_path = peers_path

    def __init__(self, node_id: str, peers_path: str) -> None:
        self.federation = self.FederationCfg(node_id, peers_path)


@contextlib.contextmanager
def authenticated_context(permissions: List[str] | None = None) -> Any:
    """Helper to set mock auth context with permissions."""
    token = active_context.set(
        RequestContext(
            user_id=uuid4(),
            username="admin_user",
            roles=["admin"],
            permissions=permissions if permissions is not None else ["platform.admin"],
            authentication_method="jwt",
        )
    )
    try:
        yield
    finally:
        active_context.reset(token)


@pytest.fixture
def temp_env() -> Any:
    """Creates temporary key, vault, and peers registry paths."""
    with (
        tempfile.NamedTemporaryFile(delete=False) as f_key,
        tempfile.NamedTemporaryFile(delete=False) as f_vault,
        tempfile.NamedTemporaryFile(delete=False) as f_peers,
    ):
        key_path = f_key.name
        vault_path = f_vault.name
        peers_path = f_peers.name
    try:
        yield key_path, vault_path, peers_path
    finally:
        for p in (key_path, vault_path, peers_path):
            if os.path.exists(p):
                os.remove(p)


def test_mock_environment_fixture(temp_env: Any) -> None:
    """Verify temp files are generated correctly."""
    key_path, vault_path, peers_path = temp_env
    assert os.path.exists(key_path)
    assert os.path.exists(vault_path)
    assert os.path.exists(peers_path)


@pytest.mark.asyncio
async def test_federation_registry_atomic_writes(temp_env: Any) -> None:
    """Verify atomic node discovery registration write integrity."""
    key_path, vault_path, peers_path = temp_env
    settings = MockSettings("node_a", peers_path)
    vault = VaultManager(key_path=key_path, secrets_path=vault_path)
    await vault.initialize()

    fed_mgr = FederationManager(settings, vault)
    await fed_mgr.initialize()

    # Register peer
    peer = await fed_mgr.register_peer("node_b", "http://localhost:8081")
    assert peer["node_id"] == "node_b"
    assert peer["base_url"] == "http://localhost:8081"

    # Read registry back to verify persistence
    peers = await fed_mgr.list_peers()
    assert len(peers) == 1
    assert peers[0]["node_id"] == "node_b"


@pytest.mark.asyncio
async def test_hmac_signatures_and_replay_protection(temp_env: Any) -> None:
    """Verify signature validation, timestamp expiration, and replay caches."""
    key_path, vault_path, peers_path = temp_env
    settings = MockSettings("node_a", peers_path)
    vault = VaultManager(key_path=key_path, secrets_path=vault_path)
    await vault.initialize()
    vault.set_secret("federation_secret", "super_secret_p2p_key")

    fed_mgr = FederationManager(settings, vault)
    await fed_mgr.initialize()

    body_bytes = b'{"msg": "hello"}'
    timestamp_str = datetime.now(timezone.utc).isoformat()
    message_id = str(uuid4())
    nonce = f"nonce_{uuid4().hex}"

    import hashlib
    import hmac

    # 1. Compute valid signature manually
    key_id = "fed_key_1"
    created_at = "2026-07-05T00:00:00Z"
    string_to_sign = (
        f"1:{message_id}:node_b:{timestamp_str}:{nonce}:{key_id}:{created_at}:"
        + body_bytes.decode("utf-8")
    )
    sig = hmac.new(
        b"super_secret_p2p_key", string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    # 2. Check successful validation
    valid = await fed_mgr.verify_signature(
        sender_node_id="node_b",
        signature=sig,
        timestamp_str=timestamp_str,
        body_bytes=body_bytes,
        key_id=key_id,
        created_at=created_at,
        message_id=message_id,
        nonce=nonce,
    )
    assert valid is True

    # 3. Check replay detection (using identical message_id or nonce fails)
    replay = await fed_mgr.verify_signature(
        sender_node_id="node_b",
        signature=sig,
        timestamp_str=timestamp_str,
        body_bytes=body_bytes,
        key_id=key_id,
        created_at=created_at,
        message_id=message_id,
        nonce=nonce,
    )
    assert replay is False

    # 4. Check expired timestamp rejection
    expired_time = datetime.now(timezone.utc).timestamp() - 600.0  # 10 minutes ago
    expired_str = datetime.fromtimestamp(expired_time, timezone.utc).isoformat()
    string_to_sign_expired = (
        f"1:{message_id}:node_b:{expired_str}:{nonce}:{key_id}:{created_at}:"
        + body_bytes.decode("utf-8")
    )
    sig_expired = hmac.new(
        b"super_secret_p2p_key",
        string_to_sign_expired.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    expired_valid = await fed_mgr.verify_signature(
        sender_node_id="node_b",
        signature=sig_expired,
        timestamp_str=expired_str,
        body_bytes=body_bytes,
        key_id=key_id,
        created_at=created_at,
        message_id=str(uuid4()),  # Fresh message ID
        nonce=f"nonce_{uuid4().hex}",  # Fresh nonce
    )
    assert expired_valid is False


@pytest.mark.asyncio
async def test_resilient_outbound_routing_via_mock(
    temp_env: Any, monkeypatch: Any
) -> None:
    """Verify outbound HTTP routing resilience and structured responses."""
    key_path, vault_path, peers_path = temp_env
    settings = MockSettings("node_a", peers_path)
    vault = VaultManager(key_path=key_path, secrets_path=vault_path)
    await vault.initialize()
    vault.set_secret("federation_secret", "super_secret_p2p_key")

    fed_mgr = FederationManager(settings, vault)
    await fed_mgr.initialize()
    await fed_mgr.register_peer("node_b", "http://peer-node-b.local")

    msg = InterAgentMessage(
        sender="Planner", receiver="Developer", action="build_task", body={}
    )

    class MockResponse:
        def __init__(self, status_code: int, text: str) -> None:
            self.status_code = status_code
            self.text = text

    # Mock success path
    async def mock_post_success(*args: Any, **kwargs: Any) -> MockResponse:
        return MockResponse(200, "OK")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_success)
    res = await fed_mgr.route_message("node_b", msg)
    assert res["status"] == "success"
    assert "latency_ms" in res

    # Mock network failure path
    async def mock_post_fail(*args: Any, **kwargs: Any) -> None:
        raise httpx.ConnectTimeout("Connection timed out.")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_fail)
    res_fail = await fed_mgr.route_message("node_b", msg)
    assert res_fail["status"] == "failed"
    assert "latency_ms" in res_fail
    assert "Connection timed out" in res_fail["reason"]


@pytest.mark.asyncio
async def test_federated_ping_peer(temp_env: Any, monkeypatch: Any) -> None:
    """Verify lightweight GET heartbeats pinging peers."""
    key_path, vault_path, peers_path = temp_env
    settings = MockSettings("node_a", peers_path)
    vault = VaultManager(key_path=key_path, secrets_path=vault_path)
    await vault.initialize()

    fed_mgr = FederationManager(settings, vault)
    await fed_mgr.initialize()
    await fed_mgr.register_peer("node_b", "http://peer-node-b.local")

    class MockResponse:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

    async def mock_get_success(*args: Any, **kwargs: Any) -> MockResponse:
        return MockResponse(200)

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get_success)
    ping = await fed_mgr.ping_peer("node_b")
    assert ping["status"] == "online"
    assert "latency_ms" in ping


def test_federation_route_gateway(temp_env: Any) -> None:
    """Verify FastAPI routing gateway mounts, signature validations, and auth scopes."""
    key_path, vault_path, peers_path = temp_env
    settings = MockSettings("node_a", peers_path)
    vault = VaultManager(key_path=key_path, secrets_path=vault_path)
    asyncio.run(vault.initialize())
    vault.set_secret("federation_secret", "super_secret_p2p_key")

    fed_mgr = FederationManager(settings, vault)
    asyncio.run(fed_mgr.initialize())

    app = FastAPI()
    app.include_router(federation_router, prefix="/api/v1")
    register_exception_handlers(app)

    app.dependency_overrides[get_federation_manager] = lambda: fed_mgr
    client = TestClient(app)

    # 1. Unauthorized admin routes check
    with authenticated_context(permissions=[]):
        assert client.get("/api/v1/federation/peers").status_code == 401
        assert (
            client.post(
                "/api/v1/federation/peers/register",
                json={"node_id": "b", "base_url": "http://b"},
            ).status_code
            == 401
        )

    # 2. Authorized admin routes check
    with authenticated_context(permissions=["platform.admin"]):
        reg_res = client.post(
            "/api/v1/federation/peers/register",
            json={"node_id": "node_b", "base_url": "http://localhost:8081"},
        )
        assert reg_res.status_code == 200
        assert reg_res.json()["data"]["node_id"] == "node_b"

        list_res = client.get("/api/v1/federation/peers")
        assert list_res.status_code == 200
        assert len(list_res.json()["data"]["peers"]) == 1

    # 3. Route inbound federation message (unsigned fails)
    msg = InterAgentMessage(
        sender="Planner", receiver="Developer", action="exec_action", body={}
    )
    res_unsigned = client.post(
        "/api/v1/federation/route", json=msg.model_dump(mode="json")
    )
    assert res_unsigned.status_code == 401

    # 4. Route inbound federation message (signed succeeds)
    import hashlib
    import hmac

    message_id = str(uuid4())
    nonce = f"nonce_{uuid4().hex}"
    timestamp_str = datetime.now(timezone.utc).isoformat()
    key_id = "fed_key_1"
    created_at = "2026-07-05T00:00:00Z"
    payload_str = msg.model_dump_json()

    string_to_sign = f"1:{message_id}:node_b:{timestamp_str}:{nonce}:{key_id}:{created_at}:{payload_str}"
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

    # Setup global event bus inside app state to catch event
    fake_bus = FakeEventBus()
    asyncio.run(fake_bus.start())
    # Register event bus in container
    from core.interfaces import EventBusInterface

    fed_mgr.event_bus = fake_bus
    # Resolve helper for router
    app.dependency_overrides[get_kernel] = lambda: type(
        "FakeKernel",
        (),
        {
            "container": type(
                "FakeContainer",
                (),
                {
                    "resolve": lambda self, t: (
                        fake_bus if t == EventBusInterface else None
                    )
                },
            )()
        },
    )()

    res_signed = client.post(
        "/api/v1/federation/route",
        json=msg.model_dump(mode="json"),
        headers=headers,
    )
    assert res_signed.status_code == 200
    assert res_signed.json()["data"]["status"] == "success"

    # Verify event published locally on FakeEventBus
    assert len(fake_bus.events) == 2
    assert fake_bus.events[0]["topic"] == "agent.Developer.message"
    assert fake_bus.events[1]["topic"] == "federation.message_received"
