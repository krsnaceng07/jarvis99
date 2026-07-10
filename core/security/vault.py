"""
PHASE: 29
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/91_PHASE_29_ADVANCED_VAULT_OPERATIONS_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/fa98328c-ff31-452a-9668-808df53aa5a3/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import base64
import hashlib
import json
import logging
import os
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from core.exceptions import JarvisSystemError

logger = logging.getLogger("jarvis.core.security.vault")


class VaultManager:
    """Manager for securely storing and retrieving secrets using local symmetric AES-256-GCM encryption."""

    def __init__(
        self,
        key_path: str,
        secrets_path: Optional[str] = None,
        event_bus: Optional[Any] = None,
    ) -> None:
        """Initialize VaultManager with a master key file path.

        Args:
            key_path: File path to the encryption master key.
            secrets_path: Optional file path to the encrypted secrets file.
            event_bus: Optional event bus instance to publish audit events.
        """
        self.key_path = key_path
        self.secrets_path = secrets_path or os.path.join(
            os.path.dirname(key_path), "vault.enc"
        )
        self.event_bus = event_bus
        self._key: Optional[bytes] = None
        self._secrets_metadata: Dict[str, Any] = {
            "version": 2,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "entries": {},
        }

    @property
    def _secrets(self) -> Dict[str, str]:
        """Backwards compatibility proxy for old direct dictionary accesses in tests."""

        class SecretsProxy(dict):
            def __init__(self, manager: VaultManager) -> None:
                self.manager = manager
                super().__init__()

            def __setitem__(self, key: str, value: str) -> None:
                key_hash = (
                    key
                    if len(key) == 64 and all(c in "0123456789abcdef" for c in key)
                    else hashlib.sha256(key.encode("utf-8")).hexdigest()
                )
                self.manager._secrets_metadata.setdefault("entries", {})[key_hash] = {
                    "ciphertext": value,
                    "key_id": "master_key_v1",
                    "algorithm": "AES-256-GCM",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }

            def __getitem__(self, key: str) -> str:
                key_hash = (
                    key
                    if len(key) == 64 and all(c in "0123456789abcdef" for c in key)
                    else hashlib.sha256(key.encode("utf-8")).hexdigest()
                )
                return self.manager._secrets_metadata["entries"][key_hash]["ciphertext"]

            def __contains__(self, key: object) -> bool:
                if not isinstance(key, str):
                    return False
                key_hash = (
                    key
                    if len(key) == 64 and all(c in "0123456789abcdef" for c in key)
                    else hashlib.sha256(key.encode("utf-8")).hexdigest()
                )
                return key_hash in self.manager._secrets_metadata.get("entries", {})

        return SecretsProxy(self)

    def is_locked(self) -> bool:
        """Return True if the vault is locked (no master key loaded).

        Used by readiness / preflight / diagnostics checks. A vault is
        considered locked when the master key has not been loaded into
        memory yet (i.e. ``initialize()`` has not run, or failed before
        loading the key). Once ``initialize()`` succeeds, ``_key`` is
        populated and the vault is unlocked.
        """
        return self._key is None

    async def initialize(self) -> None:
        """Initialize vault. Load or generate the symmetric master key and load persisted secrets.

        Raises:
            JarvisSystemError: If key directory is invalid or key load fails.
        """
        try:
            # Create directories if missing
            key_dir = os.path.dirname(self.key_path)
            if key_dir and not os.path.exists(key_dir):
                os.makedirs(key_dir, exist_ok=True)

            secrets_dir = os.path.dirname(self.secrets_path)
            if secrets_dir and not os.path.exists(secrets_dir):
                os.makedirs(secrets_dir, exist_ok=True)

            if not os.path.exists(self.key_path) or os.path.getsize(self.key_path) == 0:
                # Generate new key for development/bootstrap
                new_key = AESGCM.generate_key(bit_length=256)
                with open(self.key_path, "wb") as key_file:
                    key_file.write(base64.urlsafe_b64encode(new_key))

            with open(self.key_path, "rb") as key_file:
                encoded = key_file.read().strip()
                self._key = base64.urlsafe_b64decode(encoded)

            if not self._key or len(self._key) != 32:
                raise ValueError("Master key must be exactly 32 bytes decoded.")

            # Load secrets from disk if exists
            if (
                os.path.exists(self.secrets_path)
                and os.path.getsize(self.secrets_path) > 0
            ):
                with open(self.secrets_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        if "version" in data and "entries" in data:
                            self._secrets_metadata = data
                        else:
                            # Migrate legacy flat dict if any
                            self._secrets_metadata = {
                                "version": 2,
                                "created_at": datetime.now(timezone.utc).isoformat(),
                                "entries": {
                                    k: {
                                        "ciphertext": v,
                                        "key_id": "master_key_v1",
                                        "algorithm": "AES-256-GCM",
                                        "created_at": datetime.now(
                                            timezone.utc
                                        ).isoformat(),
                                    }
                                    for k, v in data.items()
                                },
                            }
        except Exception as err:
            raise JarvisSystemError(
                code="SYSTEM_001",
                message=f"Vault initialization failed: {str(err)}",
            ) from err

    def get_secret(self, key_name: str, agent_id: Optional[UUID] = None) -> str:
        """Retrieve a decrypted secret from the vault.

        Args:
            key_name: The identifier of the secret (e.g. 'openai_api_key').
            agent_id: Optional UUID of the requesting agent (for access logs).

        Returns:
            The decrypted secret value string.

        Raises:
            JarvisSystemError: If key is not found or decryption fails.
        """
        if not self._key:
            raise JarvisSystemError(
                code="SYSTEM_001",
                message="Vault is not initialized.",
            )

        # Hash key using SHA-256 for lookup (obfuscating secret names on disk)
        key_hash = hashlib.sha256(key_name.encode("utf-8")).hexdigest()

        entries = self._secrets_metadata.get("entries", {})

        # Use constant-time comparison to find the matching hash entry to mitigate timing attacks
        target_entry = None
        for k, v in entries.items():
            if secrets.compare_digest(k, key_hash):
                target_entry = v
                break

        if not target_entry:
            self._publish_event_sync(
                "vault.secret_accessed",
                {
                    "key_name": key_name,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "status": "failed",
                },
            )
            raise JarvisSystemError(
                code="SYSTEM_001",
                message="Secret key not found in vault.",
            )

        # Check expiration and warn
        if self.check_expiration(key_name):
            expires_at = target_entry.get("expires_at")
            logger.warning("Secret key '%s' has expired on %s", key_name, expires_at)

        encrypted_val = target_entry["ciphertext"]
        try:
            # Retrieve active key to decrypt this entry if rotation occurred
            # But in the local vault model, self._key is always the active key after rotation.
            # We will use self._key to decrypt.
            decrypted = self._decrypt(encrypted_val)
            self._publish_event_sync(
                "vault.secret_accessed",
                {
                    "key_name": key_name,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "status": "success",
                },
            )
            return decrypted
        except Exception as err:
            self._publish_event_sync(
                "vault.secret_accessed",
                {
                    "key_name": key_name,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "status": "failed",
                },
            )
            raise JarvisSystemError(
                code="SYSTEM_999",
                message=f"Failed to decrypt secret: {str(err)}",
            ) from err

    def set_secret(
        self,
        key_name: str,
        secret_value: str,
        expires_at: Optional[str] = None,
    ) -> None:
        """Encrypt and store a secret in the local vault.

        Args:
            key_name: The identifier of the secret.
            secret_value: The plaintext secret value.
            expires_at: Optional ISO-8601 expiration timestamp string.

        Raises:
            JarvisSystemError: If vault is uninitialized or encryption fails.
        """
        if not self._key:
            raise JarvisSystemError(
                code="SYSTEM_001",
                message="Vault is not initialized.",
            )

        try:
            encrypted = self._encrypt(secret_value)
            key_hash = hashlib.sha256(key_name.encode("utf-8")).hexdigest()

            # Save entry with metadata for future secret rotation
            entry: Dict[str, Any] = {
                "ciphertext": encrypted,
                "key_id": self._secrets_metadata.get("active_key_id", "master_key_v1"),
                "algorithm": "AES-256-GCM",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            if expires_at:
                # Validate ISO format
                try:
                    datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                except ValueError as val_err:
                    raise JarvisSystemError(
                        code="SYSTEM_001",
                        message=f"Invalid expires_at format: {str(val_err)}",
                    )
                entry["expires_at"] = expires_at

            self._secrets_metadata.setdefault("entries", {})[key_hash] = entry

            # Atomic vault write: write to a temporary file first, fsync, then rename
            tmp_path = self.secrets_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._secrets_metadata, f, indent=4)
                f.flush()
                os.fsync(f.fileno())

            # Atomically rename
            os.replace(tmp_path, self.secrets_path)

            self._publish_event_sync(
                "vault.secret_stored",
                {
                    "key_name": key_name,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

        except Exception as err:
            if isinstance(err, JarvisSystemError):
                raise err
            raise JarvisSystemError(
                code="SYSTEM_999",
                message=f"Failed to encrypt and store secret: {str(err)}",
            ) from err

    def check_expiration(self, key_name: str) -> bool:
        """Check if the given secret has expired.

        Returns:
            True if expired, False otherwise.
        """
        key_hash = hashlib.sha256(key_name.encode("utf-8")).hexdigest()
        entries = self._secrets_metadata.get("entries", {})

        target_entry = None
        for k, v in entries.items():
            if secrets.compare_digest(k, key_hash):
                target_entry = v
                break

        if not target_entry:
            return False

        expires_at = target_entry.get("expires_at")
        if not expires_at:
            return False

        try:
            dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            return datetime.now(timezone.utc) > dt
        except Exception:
            return False

    async def rotate_master_key(self) -> str:
        """Generate a new master key, re-encrypt all secrets, and persist them.

        Returns:
            The newly active key_id string.
        """
        if not self._key:
            raise JarvisSystemError(
                code="SYSTEM_001",
                message="Vault is not initialized.",
            )

        try:
            # 1. Generate new key
            new_key = AESGCM.generate_key(bit_length=256)
            new_key_id = f"key_{secrets.token_hex(4)}"

            # 2. Decrypt all entries and re-encrypt with new key
            updated_entries = {}
            entries = self._secrets_metadata.get("entries", {})
            for k_hash, entry in entries.items():
                ciphertext = entry["ciphertext"]
                # Decrypt using current self._key
                nonce_and_ciphertext = base64.b64decode(ciphertext.encode("utf-8"))
                if len(nonce_and_ciphertext) <= 12:
                    raise ValueError("Cipher text too short.")
                old_nonce = nonce_and_ciphertext[:12]
                old_cipher = nonce_and_ciphertext[12:]
                aesgcm_old = AESGCM(self._key)
                plain_bytes = aesgcm_old.decrypt(old_nonce, old_cipher, None)

                # Encrypt with new key
                aesgcm_new = AESGCM(new_key)
                new_nonce = os.urandom(12)
                new_ciphertext = aesgcm_new.encrypt(new_nonce, plain_bytes, None)
                new_encoded = base64.b64encode(new_nonce + new_ciphertext).decode(
                    "utf-8"
                )

                # Copy and update entry metadata
                new_entry = dict(entry)
                new_entry.update(
                    {
                        "ciphertext": new_encoded,
                        "key_id": new_key_id,
                        "algorithm": "AES-256-GCM",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                updated_entries[k_hash] = new_entry

            # 3. Transactional Write: Write key file and vault file atomically
            # Write key file atomically
            tmp_key_path = self.key_path + ".tmp"
            with open(tmp_key_path, "wb") as kf:
                kf.write(base64.urlsafe_b64encode(new_key))
                kf.flush()
                os.fsync(kf.fileno())

            # Prepare vault metadata with updated entries and metadata
            new_metadata = dict(self._secrets_metadata)
            new_metadata["entries"] = updated_entries
            new_metadata["last_rotation"] = datetime.now(timezone.utc).isoformat()
            new_metadata["active_key_id"] = new_key_id

            tmp_vault_path = self.secrets_path + ".tmp"
            with open(tmp_vault_path, "w", encoding="utf-8") as vf:
                json.dump(new_metadata, vf, indent=4)
                vf.flush()
                os.fsync(vf.fileno())

            # Atomically replace key and vault files
            os.replace(tmp_key_path, self.key_path)
            os.replace(tmp_vault_path, self.secrets_path)

            # Update in-memory values only after successful writes
            self._key = new_key
            self._secrets_metadata = new_metadata

            # Publish event
            await self._publish_event(
                "vault.key_rotated",
                {
                    "new_key_id": new_key_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

            return new_key_id
        except Exception as err:
            raise JarvisSystemError(
                code="SYSTEM_999",
                message=f"Key rotation failed: {str(err)}",
            ) from err

    def _encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext using AES-256-GCM."""
        if not self._key:
            raise ValueError("Key missing.")

        aesgcm = AESGCM(self._key)
        nonce = os.urandom(12)  # Standard 12-byte nonce for GCM
        data_bytes = plaintext.encode("utf-8")
        ciphertext = aesgcm.encrypt(nonce, data_bytes, None)

        # Combine nonce and ciphertext + tag
        return base64.b64encode(nonce + ciphertext).decode("utf-8")

    def _decrypt(self, cipher_text: str) -> str:
        """Decrypt ciphertext using AES-256-GCM."""
        if not self._key:
            raise ValueError("Key missing.")

        decoded = base64.b64decode(cipher_text.encode("utf-8"))
        if len(decoded) <= 12:
            raise ValueError("Cipher text too short.")

        nonce = decoded[:12]
        ciphertext = decoded[12:]

        aesgcm = AESGCM(self._key)
        plain_bytes = aesgcm.decrypt(nonce, ciphertext, None)
        return plain_bytes.decode("utf-8")

    async def _publish_event(self, topic: str, msg: Dict[str, Any]) -> None:
        """Asynchronously publish an audit event to the event bus."""
        if self.event_bus:
            try:
                await self.event_bus.publish(topic, msg)
            except Exception as e:
                logger.error("Failed to publish event %s: %s", topic, str(e))

    def _publish_event_sync(self, topic: str, msg: Dict[str, Any]) -> None:
        """Synchronously dispatch audit event to the running event loop."""
        if self.event_bus:
            import asyncio

            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    loop.create_task(self.event_bus.publish(topic, msg))
            except RuntimeError:
                pass
