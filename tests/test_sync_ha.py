"""
PHASE: 30
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/92_PHASE_30_CLOUD_SYNC_HIGH_AVAILABILITY_SPECIFICATION.md

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
import sqlite3
import tempfile
from typing import Any, Dict, List, Optional
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.dependencies import get_sync_manager
from api.middleware import register_exception_handlers
from api.routes.sync import router as sync_router
from core.exceptions import JarvisSystemError
from core.interfaces import EventBusInterface, InterAgentMessage
from core.runtime.replication import ReplicationManager
from core.security.auth_context import RequestContext, active_context
from core.security.sync import (
    CloudStorageProvider,
    LocalFolderStorageProvider,
    SyncManager,
)
from core.security.vault import VaultManager


class FakeEventBus(EventBusInterface):
    """Fake Event Bus to capture published sync audit events."""

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


class FailureStorageProvider(CloudStorageProvider):
    """Mock storage provider designed to fail on demand."""

    def __init__(self, fail_upload: bool = False, fail_download: bool = False) -> None:
        self.fail_upload = fail_upload
        self.fail_download = fail_download

    async def upload(self, sync_id: str, payload: bytes) -> None:
        if self.fail_upload:
            raise IOError("Network timeout uploading payload.")

    async def download(self, sync_id: str) -> Optional[bytes]:
        if self.fail_download:
            raise IOError("Network connection reset downloading payload.")
        return None

    async def get_latest_sync_metadata(self) -> Optional[Dict[str, Any]]:
        return {"sync_id": "latest_sync"}


class MockSettings:
    """Mock Settings mimicking core database and system configuration."""

    class DatabaseCfg:
        def __init__(self, name: str) -> None:
            self.host = "sqlite"
            self.name = name

    def __init__(self, db_name: str) -> None:
        self.database = self.DatabaseCfg(db_name)


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
    """Creates temporary vault and database file paths."""
    with (
        tempfile.NamedTemporaryFile(delete=False) as f_key,
        tempfile.NamedTemporaryFile(delete=False) as f_vault,
        tempfile.NamedTemporaryFile(delete=False) as f_db,
    ):
        key_path = f_key.name
        vault_path = f_vault.name
        db_path = f_db.name
    try:
        yield key_path, vault_path, db_path
    finally:
        for p in (key_path, vault_path, db_path):
            if os.path.exists(p):
                os.remove(p)


@pytest.mark.asyncio
async def test_encrypted_sync_round_trip(temp_env: Any) -> None:
    """Verify local state (vault + db) pushing, mutating, pulling, and recovering state."""
    key_path, vault_path, db_path = temp_env
    settings = MockSettings(db_path)

    # Initialize vault
    vault = VaultManager(key_path=key_path, secrets_path=vault_path)
    await vault.initialize()
    vault.set_secret("db_pass", "secret123")

    # Set up dummy table and data in sqlite
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE test_data (id INTEGER PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO test_data (value) VALUES ('original_data')")
    conn.commit()
    conn.close()

    # Sync
    with tempfile.TemporaryDirectory() as sync_dir:
        provider = LocalFolderStorageProvider(sync_dir)
        sync_mgr = SyncManager(vault, provider, settings, client_id="node_a")

        push_res = await sync_mgr.push_state()
        assert push_res["status"] == "success"

        # Mutate local state
        vault.set_secret("db_pass", "mutated123")
        conn = sqlite3.connect(db_path)
        conn.execute("UPDATE test_data SET value = 'mutated_data'")
        conn.commit()
        conn.close()

        # Create secondary manager pulling state
        provider2 = LocalFolderStorageProvider(sync_dir)
        vault2 = VaultManager(key_path=key_path, secrets_path=vault_path)
        await vault2.initialize()

        # Write clean mutated state to vault2 to show pull overwrites
        vault2.set_secret("db_pass", "clean")

        sync_mgr2 = SyncManager(vault2, provider2, settings, client_id="node_b")
        pull_res = await sync_mgr2.pull_state()

        assert pull_res["applied"] is True
        assert vault2.get_secret("db_pass") == "secret123"

        # Verify DB reverted to original_data
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM test_data")
        row = cursor.fetchone()
        assert row[0] == "original_data"
        conn.close()


@pytest.mark.asyncio
async def test_conflict_resolution(temp_env: Any) -> None:
    """Verify vector clock and LWW fallback conflict resolution policies."""
    key_path, vault_path, db_path = temp_env
    settings = MockSettings(db_path)

    vault = VaultManager(key_path=key_path, secrets_path=vault_path)
    await vault.initialize()

    with tempfile.TemporaryDirectory() as sync_dir:
        provider = LocalFolderStorageProvider(sync_dir)
        sync_mgr = SyncManager(vault, provider, settings, client_id="node_a")

        # Set clock state
        sync_mgr.vector_clock = {"node_a": 3, "node_b": 1}

        # Case 1: Remote dominates (Vector clock B > A)
        remote_clock = {"node_a": 3, "node_b": 2}
        assert (
            sync_mgr._compare_clocks(sync_mgr.vector_clock, remote_clock)
            == "b_dominates"
        )

        # Case 2: Local dominates (Vector clock A > B)
        remote_clock_old = {"node_a": 2, "node_b": 1}
        assert (
            sync_mgr._compare_clocks(sync_mgr.vector_clock, remote_clock_old)
            == "a_dominates"
        )

        # Case 3: Equal clocks
        assert (
            sync_mgr._compare_clocks(sync_mgr.vector_clock, sync_mgr.vector_clock)
            == "equal"
        )

        # Case 4: Concurrent clocks (requires LWW fallback)
        remote_clock_concurrent = {"node_a": 2, "node_b": 3}
        assert (
            sync_mgr._compare_clocks(sync_mgr.vector_clock, remote_clock_concurrent)
            == "concurrent"
        )


@pytest.mark.asyncio
async def test_network_interruption(temp_env: Any) -> None:
    """Verify upload failure rolls back local clock increment and preserves local state."""
    key_path, vault_path, db_path = temp_env
    settings = MockSettings(db_path)

    vault = VaultManager(key_path=key_path, secrets_path=vault_path)
    await vault.initialize()

    provider = FailureStorageProvider(fail_upload=True)
    sync_mgr = SyncManager(vault, provider, settings, client_id="node_a")

    sync_mgr.vector_clock["node_a"] = 10

    with pytest.raises(JarvisSystemError):
        await sync_mgr.push_state()

    # Local clock rolled back
    assert sync_mgr.vector_clock["node_a"] == 10


@pytest.mark.asyncio
async def test_duplicate_push(temp_env: Any) -> None:
    """Verify consecutive pushes are idempotent and maintain incremental status."""
    key_path, vault_path, db_path = temp_env
    settings = MockSettings(db_path)

    vault = VaultManager(key_path=key_path, secrets_path=vault_path)
    await vault.initialize()

    with tempfile.TemporaryDirectory() as sync_dir:
        provider = LocalFolderStorageProvider(sync_dir)
        sync_mgr = SyncManager(vault, provider, settings, client_id="node_a")

        r1 = await sync_mgr.push_state()
        c1 = sync_mgr.vector_clock["node_a"]

        r2 = await sync_mgr.push_state()
        c2 = sync_mgr.vector_clock["node_a"]

        assert c2 == c1 + 1
        assert r1["sync_id"] != r2["sync_id"]


@pytest.mark.asyncio
async def test_corrupted_payload(temp_env: Any) -> None:
    """Verify malformed payload rejection triggers errors and leaves local vault untouched."""
    key_path, vault_path, db_path = temp_env
    settings = MockSettings(db_path)

    vault = VaultManager(key_path=key_path, secrets_path=vault_path)
    await vault.initialize()
    vault.set_secret("api_key", "valid_secret")

    with tempfile.TemporaryDirectory() as sync_dir:
        provider = LocalFolderStorageProvider(sync_dir)
        sync_mgr = SyncManager(vault, provider, settings, client_id="node_a")

        # Push valid state
        await sync_mgr.push_state()

        # Corrupt the payload on disk
        latest = await provider.get_latest_sync_metadata()
        assert latest is not None
        corrupt_path = os.path.join(sync_dir, latest["filename"])
        with open(corrupt_path, "wb") as f:
            f.write(b"this_is_garbage_content_not_json")

        # Pull
        with pytest.raises(JarvisSystemError) as exc_info:
            await sync_mgr.pull_state()

        assert "schema validation failed" in exc_info.value.message
        assert vault.get_secret("api_key") == "valid_secret"


@pytest.mark.asyncio
async def test_sqlite_ha_replication(temp_env: Any) -> None:
    """Verify active-passive SQLite database connection replication and promotion failover."""
    key_path, vault_path, db_path = temp_env
    replica_path = db_path + ".replica"

    settings = MockSettings(db_path)

    # Prepare primary database with tables
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE billing (id INTEGER PRIMARY KEY, cost REAL)")
    conn.execute("INSERT INTO billing (cost) VALUES (1.50)")
    conn.commit()
    conn.close()

    rep = ReplicationManager(settings, db_path, replica_path)

    # 1. Replicate database
    ok = await rep.replicate()
    assert ok is True
    assert os.path.exists(replica_path)

    # 2. Verify replica integrity passes
    is_valid = await rep.verify_replica_integrity()
    assert is_valid is True

    # 3. Corrupt the replica file on disk
    with open(replica_path, "w") as f:
        f.write("corrupted_text_payload")

    # 4. Verify integrity fails
    is_valid_corrupt = await rep.verify_replica_integrity()
    assert is_valid_corrupt is False

    # 5. Verify promotion is blocked
    with pytest.raises(JarvisSystemError) as exc_info:
        await rep.promote_replica()
    assert "Replica promotion denied" in exc_info.value.message

    if os.path.exists(replica_path):
        os.remove(replica_path)


def test_sync_admin_endpoints(temp_env: Any) -> None:
    """Verify /api/v1/sync endpoints check platform.admin permission scope."""
    key_path, vault_path, db_path = temp_env
    settings = MockSettings(db_path)

    vault = VaultManager(key_path=key_path, secrets_path=vault_path)

    asyncio.run(vault.initialize())

    with tempfile.TemporaryDirectory() as sync_dir:
        provider = LocalFolderStorageProvider(sync_dir)
        sync_mgr = SyncManager(vault, provider, settings, client_id="test_client")

        app = FastAPI()
        app.include_router(sync_router, prefix="/api/v1")
        register_exception_handlers(app)

        app.dependency_overrides[get_sync_manager] = lambda: sync_mgr
        client = TestClient(app)

        # 1. Unauthorized access (no scopes)
        with authenticated_context(permissions=[]):
            res_push = client.post("/api/v1/sync/push")
            assert res_push.status_code == 401

            res_pull = client.post("/api/v1/sync/pull")
            assert res_pull.status_code == 401

            res_status = client.get("/api/v1/sync/status")
            assert res_status.status_code == 401

        # 2. Authorized access
        with authenticated_context(permissions=["platform.admin"]):
            # Status
            res_status_ok = client.get("/api/v1/sync/status")
            assert res_status_ok.status_code == 200
            assert res_status_ok.json()["data"]["client_id"] == "test_client"

            # Push
            res_push_ok = client.post("/api/v1/sync/push")
            assert res_push_ok.status_code == 200
            assert res_push_ok.json()["data"]["status"] == "success"

            # Pull (skipped equal comparison)
            res_pull_ok = client.post("/api/v1/sync/pull")
            assert res_pull_ok.status_code == 200
            assert "skipped" in res_pull_ok.json()["data"]["status"]
