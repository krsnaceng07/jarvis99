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

import base64
import json
import logging
import os
import sqlite3
import tempfile
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.exceptions import JarvisSystemError
from core.interfaces import EventBusInterface, InterAgentMessage
from core.security.vault import VaultManager

logger = logging.getLogger(__name__)


class CloudStorageProvider(ABC):
    """Abstract interface for cloud sync transport layer."""

    @abstractmethod
    async def upload(self, sync_id: str, payload: bytes) -> None:
        """Upload sync payload to remote storage."""

    @abstractmethod
    async def download(self, sync_id: str) -> Optional[bytes]:
        """Download sync payload from remote storage."""

    @abstractmethod
    async def get_latest_sync_metadata(self) -> Optional[Dict[str, Any]]:
        """Retrieve metadata for the latest uploaded sync package."""


class LocalFolderStorageProvider(CloudStorageProvider):
    """Local folder implementation of CloudStorageProvider for testing/development."""

    def __init__(self, folder_path: str) -> None:
        self.folder_path = folder_path
        os.makedirs(folder_path, exist_ok=True)

    async def upload(self, sync_id: str, payload: bytes) -> None:
        file_path = os.path.join(self.folder_path, f"{sync_id}.sync")
        with open(file_path, "wb") as f:
            f.write(payload)

        # Update latest pointer atomically
        meta_path = os.path.join(self.folder_path, "latest.json")
        meta = {
            "sync_id": sync_id,
            "filename": f"{sync_id}.sync",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        temp_meta = meta_path + ".tmp"
        with open(temp_meta, "w", encoding="utf-8") as f:
            json.dump(meta, f)
        os.replace(temp_meta, meta_path)

    async def download(self, sync_id: str) -> Optional[bytes]:
        file_path = os.path.join(self.folder_path, f"{sync_id}.sync")
        if not os.path.exists(file_path):
            return None
        with open(file_path, "rb") as f:
            return f.read()

    async def get_latest_sync_metadata(self) -> Optional[Dict[str, Any]]:
        meta_path = os.path.join(self.folder_path, "latest.json")
        if not os.path.exists(meta_path):
            return None
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None


class SyncManager:
    """Manages secure state synchronization using vector clocks and AES-256-GCM encryption."""

    def __init__(
        self,
        vault_manager: VaultManager,
        storage_provider: CloudStorageProvider,
        settings: Any,
        client_id: Optional[str] = None,
        event_bus: Optional[EventBusInterface] = None,
    ) -> None:
        self.vault_manager = vault_manager
        self.storage_provider = storage_provider
        self.settings = settings
        self.client_id = client_id or f"node_{uuid4().hex[:8]}"
        self.event_bus = event_bus
        self.vector_clock: Dict[str, int] = {self.client_id: 0}
        self.last_sync_timestamp: Optional[str] = None

    async def _publish_event(self, topic: str, data: Dict[str, Any]) -> None:
        if self.event_bus:
            try:
                # InterAgentMessage schema (core/interfaces.py) requires:
                #   sender, receiver, action, body
                # Earlier versions of this code used legacy field names
                # (``target``, ``content``) which Pydantic now rejects with
                # 3 validation errors on every sync event. Map the topic +
                # payload to the canonical schema.
                msg = InterAgentMessage(
                    id=uuid4(),
                    sender=f"sync_manager_{self.client_id}",
                    receiver="*",
                    action=topic,
                    body=data,
                )
                await self.event_bus.publish(topic, msg)
            except Exception as e:
                logger.error("Failed to publish sync event %s: %s", topic, e)

    def _compare_clocks(self, clock_a: Dict[str, int], clock_b: Dict[str, int]) -> str:
        all_keys = set(clock_a.keys()) | set(clock_b.keys())
        a_greater = False
        b_greater = False
        for k in all_keys:
            val_a = clock_a.get(k, 0)
            val_b = clock_b.get(k, 0)
            if val_a > val_b:
                a_greater = True
            elif val_b > val_a:
                b_greater = True

        if a_greater and b_greater:
            return "concurrent"
        if a_greater:
            return "a_dominates"
        if b_greater:
            return "b_dominates"
        return "equal"

    async def push_state(self) -> Dict[str, Any]:
        """Encrypts vault metadata and persistent SQLite DB, pushing them to remote storage."""
        if not self.vault_manager._key:
            raise JarvisSystemError(
                code="SYSTEM_001",
                message="Vault is not initialized.",
            )

        # 1. Read memory db bytes if sqlite
        db_bytes = b""
        db_path = self.settings.database.name
        if (
            self.settings.database.host == "sqlite"
            and db_path != ":memory:"
            and os.path.exists(db_path)
        ):
            try:
                with open(db_path, "rb") as f:
                    db_bytes = f.read()
            except Exception as e:
                raise JarvisSystemError(
                    code="SYSTEM_999",
                    message=f"Failed reading database for sync: {str(e)}",
                )

        # 2. Package inner state
        vault_data = self.vault_manager._secrets_metadata
        inner_payload = {
            "vault": vault_data,
            "memory_db": base64.b64encode(db_bytes).decode("utf-8"),
        }
        inner_str = json.dumps(inner_payload)

        # 3. Encrypt payload using GCM
        try:
            aesgcm = AESGCM(self.vault_manager._key)
            nonce = os.urandom(12)
            ciphertext = aesgcm.encrypt(nonce, inner_str.encode("utf-8"), None)
        except Exception as e:
            raise JarvisSystemError(
                code="SYSTEM_999",
                message=f"Sync encryption failed: {str(e)}",
            )

        # 4. Increment local clock
        self.vector_clock[self.client_id] = self.vector_clock.get(self.client_id, 0) + 1
        self.last_sync_timestamp = datetime.now(timezone.utc).isoformat()
        sync_id = f"sync_{uuid4().hex[:12]}"

        # 5. Form Sync Envelope
        envelope = {
            "schema_version": 1,
            "client_id": self.client_id,
            "sync_id": sync_id,
            "vector_clock": dict(self.vector_clock),
            "timestamp": self.last_sync_timestamp,
            "vault_version": vault_data.get("version", 2) if vault_data else 2,
            "memory_version": 1,
            "ciphertext": base64.b64encode(ciphertext).decode("utf-8"),
            "nonce": base64.b64encode(nonce).decode("utf-8"),
            "algorithm": "AES-256-GCM",
        }

        # 6. Upload
        try:
            payload_bytes = json.dumps(envelope).encode("utf-8")
            await self.storage_provider.upload(sync_id, payload_bytes)
        except Exception as e:
            # Rollback local clock increment to prevent state drift on connection failure
            self.vector_clock[self.client_id] -= 1
            raise JarvisSystemError(
                code="SYSTEM_999",
                message=f"Sync upload failed: {str(e)}",
            )

        await self._publish_event(
            "sync.pushed", {"sync_id": sync_id, "client_id": self.client_id}
        )

        return {
            "status": "success",
            "sync_id": sync_id,
            "vector_clock": dict(self.vector_clock),
        }

    async def pull_state(self) -> Dict[str, Any]:
        """Pulls remote state, decrypts, runs conflict resolution, and applies atomically."""
        if not self.vault_manager._key:
            raise JarvisSystemError(
                code="SYSTEM_001",
                message="Vault is not initialized.",
            )

        # 1. Fetch latest metadata
        meta = await self.storage_provider.get_latest_sync_metadata()
        if not meta:
            return {"status": "no_remote_state", "applied": False}

        sync_id = meta["sync_id"]

        # 2. Download envelope
        envelope_bytes = await self.storage_provider.download(sync_id)
        if not envelope_bytes:
            return {"status": "not_found", "applied": False}

        # 3. Parse and validate schema
        try:
            envelope = json.loads(envelope_bytes.decode("utf-8"))
            if not all(
                k in envelope
                for k in (
                    "schema_version",
                    "client_id",
                    "sync_id",
                    "vector_clock",
                    "timestamp",
                    "ciphertext",
                    "nonce",
                )
            ):
                raise ValueError("Envelope is missing required fields.")
        except Exception as e:
            raise JarvisSystemError(
                code="SYSTEM_999",
                message=f"Sync payload schema validation failed: {str(e)}",
            )

        # 4. Decrypt payload
        try:
            aesgcm = AESGCM(self.vault_manager._key)
            nonce = base64.b64decode(envelope["nonce"])
            ciphertext = base64.b64decode(envelope["ciphertext"])
            plain_bytes = aesgcm.decrypt(nonce, ciphertext, None)
            inner_payload = json.loads(plain_bytes.decode("utf-8"))
        except Exception as e:
            raise JarvisSystemError(
                code="SYSTEM_999",
                message=f"Decryption of sync payload failed: {str(e)}",
            )

        # Validate inner payload shape
        if "vault" not in inner_payload or "memory_db" not in inner_payload:
            raise JarvisSystemError(
                code="SYSTEM_999",
                message="Divergent or corrupted sync payload structure.",
            )

        # 5. Resolve conflict using Vector Clocks
        remote_clock = envelope["vector_clock"]
        comparison = self._compare_clocks(self.vector_clock, remote_clock)

        apply_remote = False
        if comparison == "b_dominates":
            apply_remote = True
        elif comparison == "a_dominates":
            apply_remote = False
        elif comparison == "equal":
            apply_remote = False
        else:
            # Concurrent: Fall back to LWW
            remote_time = envelope["timestamp"]
            local_time = self.last_sync_timestamp

            if not local_time:
                apply_remote = True
            elif remote_time > local_time:
                apply_remote = True
            elif remote_time < local_time:
                apply_remote = False
            else:
                # Deterministic tie-breaker: Smallest client_id wins
                apply_remote = envelope["client_id"] < self.client_id

        if not apply_remote:
            return {
                "status": f"skipped_{comparison}",
                "applied": False,
                "vector_clock": dict(self.vector_clock),
            }

        # 6. Validate Integrity of pulled states before committing
        # 6.1 Validate Vault Structure
        vault_payload = inner_payload["vault"]
        if not isinstance(vault_payload, dict) or "entries" not in vault_payload:
            raise JarvisSystemError(
                code="SYSTEM_999",
                message="Invalid vault backup structure in payload.",
            )

        # 6.2 Validate Memory DB Integrity
        db_bytes = base64.b64decode(inner_payload["memory_db"])
        db_path = self.settings.database.name

        if self.settings.database.host == "sqlite" and db_path != ":memory:":
            temp_db_fd, temp_db_path = tempfile.mkstemp(suffix=".db")
            try:
                os.write(temp_db_fd, db_bytes)
                os.close(temp_db_fd)

                # Verify integrity
                conn = sqlite3.connect(temp_db_path)
                try:
                    cursor = conn.cursor()
                    cursor.execute("PRAGMA integrity_check")
                    res = cursor.fetchone()
                    if not res or res[0] != "ok":
                        raise ValueError(f"SQLite integrity check failed: {res}")
                finally:
                    conn.close()
            except Exception as e:
                if os.path.exists(temp_db_path):
                    os.remove(temp_db_path)
                raise JarvisSystemError(
                    code="SYSTEM_999",
                    message=f"Database integrity verification failed: {str(e)}",
                )
        else:
            temp_db_path = None

        # 7. Apply State Atomically (failed sync never partially overwrites local state)
        try:
            # 7.1 Commit Vault to disk atomically
            temp_vault_path = self.vault_manager.secrets_path + ".tmp"
            with open(temp_vault_path, "w", encoding="utf-8") as f:
                json.dump(vault_payload, f)
            os.replace(temp_vault_path, self.vault_manager.secrets_path)

            # In-memory update
            self.vault_manager._secrets_metadata = vault_payload

            # 7.2 Commit DB to disk atomically
            if temp_db_path:
                os.replace(temp_db_path, db_path)

            # 7.3 Merge vector clocks
            for k, val in remote_clock.items():
                self.vector_clock[k] = max(self.vector_clock.get(k, 0), val)
            self.vector_clock[self.client_id] = (
                self.vector_clock.get(self.client_id, 0) + 1
            )
            self.last_sync_timestamp = envelope["timestamp"]

        except Exception as e:
            if temp_db_path and os.path.exists(temp_db_path):
                os.remove(temp_db_path)
            raise JarvisSystemError(
                code="SYSTEM_999",
                message=f"Atomic sync commit failed: {str(e)}",
            )

        await self._publish_event(
            "sync.pulled", {"sync_id": sync_id, "status": "applied"}
        )

        return {
            "status": "applied",
            "applied": True,
            "sync_id": sync_id,
            "vector_clock": dict(self.vector_clock),
        }
