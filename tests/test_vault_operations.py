"""JARVIS OS - Vault Operations Unit and Integration Tests.

Verifies key rotation, expiration checking, backup/restore, audit logging,
and REST route permissions.
"""

import asyncio
import contextlib
import copy
import json
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_vault_manager
from api.middleware import register_exception_handlers
from api.routes.vault import router as vault_router
from core.exceptions import JarvisSystemError
from core.interfaces import EventBusInterface, InterAgentMessage
from core.security.auth_context import RequestContext, active_context
from core.security.vault import VaultManager


class FakeEventBus(EventBusInterface):
    """Fake Event Bus for capturing published events."""

    def __init__(self) -> None:
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
        return "sub-id"

    async def unsubscribe(self, topic: str, callback: Any) -> None:
        pass


@contextlib.contextmanager
def authenticated_context(permissions: List[str] | None = None) -> Any:
    """Sets up user context with specific permissions."""
    token = active_context.set(
        RequestContext(
            user_id=uuid4(),
            username="admin_user",
            roles=["admin"],
            permissions=permissions if permissions is not None else ["vault.admin"],
            authentication_method="jwt",
        )
    )
    try:
        yield
    finally:
        active_context.reset(token)


@pytest.fixture
def temp_vault_paths() -> Any:
    """Fixture creating temporary file paths for keys and vault files."""
    with (
        tempfile.NamedTemporaryFile(delete=False) as f_key,
        tempfile.NamedTemporaryFile(delete=False) as f_vault,
    ):
        key_path = f_key.name
        vault_path = f_vault.name
    try:
        yield key_path, vault_path
    finally:
        if os.path.exists(key_path):
            os.remove(key_path)
        if os.path.exists(vault_path):
            os.remove(vault_path)


@pytest.mark.asyncio
async def test_key_rotation(temp_vault_paths: Any) -> None:
    """Verify master key rotation updates key files and re-encrypts entries."""
    key_path, vault_path = temp_vault_paths
    event_bus = FakeEventBus()

    vault = VaultManager(
        key_path=key_path, secrets_path=vault_path, event_bus=event_bus
    )
    await vault.initialize()

    vault.set_secret("openai_key", "sk-12345")
    vault.set_secret("redis_password", "my-redis-pass")

    # Rotate key
    new_key_id = await vault.rotate_master_key()
    assert new_key_id.startswith("key_")

    # Verify secrets remain decryptable
    assert vault.get_secret("openai_key") == "sk-12345"
    assert vault.get_secret("redis_password") == "my-redis-pass"

    # Check key file and vault files on disk
    with open(vault_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["active_key_id"] == new_key_id
    assert "last_rotation" in data

    # Verify event bus logged rotation
    rotation_events = [
        e for e in event_bus.published_events if e["topic"] == "vault.key_rotated"
    ]
    assert len(rotation_events) == 1
    assert rotation_events[0]["message"]["new_key_id"] == new_key_id


@pytest.mark.asyncio
async def test_expiration_metadata(
    temp_vault_paths: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """Verify secrets expiration warning logs and check_expiration functionality."""
    key_path, vault_path = temp_vault_paths
    vault = VaultManager(key_path=key_path, secrets_path=vault_path)
    await vault.initialize()

    future_exp = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    past_exp = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

    vault.set_secret("valid_key", "val1", expires_at=future_exp)
    vault.set_secret("expired_key", "val2", expires_at=past_exp)

    # Assert check_expiration
    assert vault.check_expiration("valid_key") is False
    assert vault.check_expiration("expired_key") is True

    # Get valid secret (no warning)
    with caplog.at_level(logging.WARNING):
        val1 = vault.get_secret("valid_key")
        assert val1 == "val1"
        assert not any("expired" in record.message for record in caplog.records)

    # Get expired secret (triggers warning log)
    with caplog.at_level(logging.WARNING):
        val2 = vault.get_secret("expired_key")
        assert val2 == "val2"
        assert any("expired_key" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_audit_logging(temp_vault_paths: Any) -> None:
    """Verify non-sensitive audit events are published on read and write."""
    key_path, vault_path = temp_vault_paths
    event_bus = FakeEventBus()

    vault = VaultManager(
        key_path=key_path, secrets_path=vault_path, event_bus=event_bus
    )
    await vault.initialize()

    vault.set_secret("secret_a", "valA")
    await asyncio.sleep(0.01)  # Yield loop to allow task publication

    assert any(
        e["topic"] == "vault.secret_stored" and e["message"]["key_name"] == "secret_a"
        for e in event_bus.published_events
    )

    event_bus.published_events.clear()

    # Successful read
    _ = vault.get_secret("secret_a")
    await asyncio.sleep(0.01)  # Yield loop to allow task publication

    assert any(
        e["topic"] == "vault.secret_accessed"
        and e["message"]["key_name"] == "secret_a"
        and e["message"]["status"] == "success"
        for e in event_bus.published_events
    )

    # Ensure no plaintext secrets are logged in event messages
    for event in event_bus.published_events:
        msg_str = json.dumps(event)
        assert "valA" not in msg_str


@pytest.mark.asyncio
async def test_backup_and_restore(temp_vault_paths: Any) -> None:
    """Verify vault state backup and restore atomic replacement."""
    key_path, vault_path = temp_vault_paths
    vault = VaultManager(key_path=key_path, secrets_path=vault_path)
    await vault.initialize()

    vault.set_secret("key1", "val1")
    backup = copy.deepcopy(vault._secrets_metadata)

    # Add another secret
    vault.set_secret("key2", "val2")

    # Restore backup
    vault2 = VaultManager(key_path=key_path, secrets_path=vault_path)
    await vault2.initialize()

    # Simulate REST restore overwrite
    tmp_path = vault_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(backup, f)
    os.replace(tmp_path, vault_path)

    await vault2.initialize()

    # Verify key1 restored, key2 is missing
    assert vault2.get_secret("key1") == "val1"
    with pytest.raises(JarvisSystemError):
        vault2.get_secret("key2")


@pytest.fixture
def api_test_client(temp_vault_paths: Any) -> Any:
    """Fixture creating API TestClient with mocked VaultManager dependency."""
    key_path, vault_path = temp_vault_paths
    vault = VaultManager(key_path=key_path, secrets_path=vault_path)

    app = FastAPI()
    app.include_router(vault_router, prefix="/api/v1")

    # Register standard exception handlers
    register_exception_handlers(app)

    app.dependency_overrides[get_vault_manager] = lambda: vault
    client = TestClient(app)
    return client, vault


def test_vault_admin_api_auth(api_test_client: Any) -> None:
    """Verify admin endpoints reject requests without vault.admin permission."""
    client, vault = api_test_client

    # Case 1: Unauthorized (returns 401 per standard AuthenticationError handler)
    with authenticated_context(permissions=[]):
        res = client.post("/api/v1/vault/rotate")
        assert res.status_code == 401

    # Case 2: Authorized
    with authenticated_context(permissions=["vault.admin"]):
        # Mock vault initialization
        import asyncio

        asyncio.run(vault.initialize())

        # Rotate
        res_rotate = client.post("/api/v1/vault/rotate")
        assert res_rotate.status_code == 200
        assert res_rotate.json()["data"]["status"] == "success"

        # Backup
        res_backup = client.post("/api/v1/vault/backup")
        assert res_backup.status_code == 200
        backup_data = res_backup.json()["data"]["backup_data"]
        assert backup_data["version"] == 2

        # Restore
        res_restore = client.post(
            "/api/v1/vault/restore", json={"backup_data": backup_data}
        )
        assert res_restore.status_code == 200
        assert res_restore.json()["data"]["status"] == "success"
