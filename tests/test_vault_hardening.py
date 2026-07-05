"""JARVIS OS - Security Vault Hardening Unit Tests.

Verifies AES-256-GCM ciphers, key hashing, persistence, config reference resolution,
and all security failure/negative cases (Architect constraints 1-8).
"""

import base64
import json
import os
import tempfile

import pytest

from core.config import Settings
from core.exceptions import JarvisSystemError
from core.kernel import Kernel
from core.security.vault import VaultManager


@pytest.mark.asyncio
async def test_aes_gcm_cipher_roundtrip() -> None:
    """Verify AES-256-GCM encryption and decryption round-trip."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        temp_key_path = f.name

    try:
        vault = VaultManager(key_path=temp_key_path)
        await vault.initialize()

        secret_val = "sensitive_data_123"
        encrypted = vault._encrypt(secret_val)

        # Ensure base64 structure and nonce prepended
        decoded = base64.b64decode(encrypted.encode("utf-8"))
        assert len(decoded) > 12  # 12 bytes nonce + cipher + tag

        decrypted = vault._decrypt(encrypted)
        assert decrypted == secret_val
    finally:
        os.remove(temp_key_path)


@pytest.mark.asyncio
async def test_vault_key_hashing() -> None:
    """Verify secret identifiers are hashed and not stored in plaintext."""
    with (
        tempfile.NamedTemporaryFile(delete=False) as f_key,
        tempfile.NamedTemporaryFile(delete=False) as f_secrets,
    ):
        temp_key = f_key.name
        temp_secrets = f_secrets.name

    try:
        vault = VaultManager(key_path=temp_key, secrets_path=temp_secrets)
        await vault.initialize()

        secret_key = "my_private_key"
        vault.set_secret(secret_key, "secret_value")

        # Read persisted file from disk
        with open(temp_secrets, "r", encoding="utf-8") as f:
            saved_data = json.load(f)

        # Plaintext key should not be in the persisted JSON file
        assert secret_key not in saved_data["entries"]

        # Hashed key should be present
        import hashlib

        key_hash = hashlib.sha256(secret_key.encode("utf-8")).hexdigest()
        assert key_hash in saved_data["entries"]
        assert saved_data["version"] == 2
        assert saved_data["entries"][key_hash]["algorithm"] == "AES-256-GCM"
    finally:
        os.remove(temp_key)
        os.remove(temp_secrets)


@pytest.mark.asyncio
async def test_secrets_persistence_and_reload() -> None:
    """Verify secrets are successfully persisted and reloaded from disk."""
    with (
        tempfile.NamedTemporaryFile(delete=False) as f_key,
        tempfile.NamedTemporaryFile(delete=False) as f_secrets,
    ):
        temp_key = f_key.name
        temp_secrets = f_secrets.name

    try:
        # Create first vault instance and store secret
        vault = VaultManager(key_path=temp_key, secrets_path=temp_secrets)
        await vault.initialize()
        vault.set_secret("my_key", "my_val")

        # Create second vault instance loading from same paths
        vault2 = VaultManager(key_path=temp_key, secrets_path=temp_secrets)
        await vault2.initialize()

        # Secret must be loaded successfully
        assert vault2.get_secret("my_key") == "my_val"
    finally:
        os.remove(temp_key)
        os.remove(temp_secrets)


@pytest.mark.asyncio
async def test_config_vault_reference_resolution() -> None:
    """Verify config vault:// reference resolution during kernel boot."""
    with (
        tempfile.NamedTemporaryFile(delete=False) as f_key,
        tempfile.NamedTemporaryFile(delete=False) as f_secrets,
    ):
        temp_key = f_key.name
        temp_secrets = f_secrets.name

    try:
        vault = VaultManager(key_path=temp_key, secrets_path=temp_secrets)
        await vault.initialize()
        vault.set_secret("db_password", "my_secret_db_pass")

        # Mock kernel and container
        kernel = Kernel()
        await kernel.initialize()
        kernel.container.register_singleton(VaultManager, vault)

        settings = Settings()
        settings.database.password = "vault://db_password"

        # Resolve
        kernel._resolve_vault_secrets(settings)

        # Database config should be resolved
        assert settings.database.password == "my_secret_db_pass"
    finally:
        os.remove(temp_key)
        os.remove(temp_secrets)


@pytest.mark.asyncio
async def test_negative_corrupted_ciphertext() -> None:
    """Verify corrupted ciphertext raises decrypter JarvisSystemError (Architect Coverage #8)."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        temp_key_path = f.name
    try:
        vault = VaultManager(key_path=temp_key_path)
        await vault.initialize()

        # Set a corrupt ciphertext directly in _secrets proxy
        vault._secrets["corrupt_key"] = base64.b64encode(os.urandom(30)).decode("utf-8")

        with pytest.raises(JarvisSystemError) as exc_info:
            vault.get_secret("corrupt_key")
        assert exc_info.value.code == "SYSTEM_999"
        assert "Failed to decrypt secret" in exc_info.value.message
    finally:
        os.remove(temp_key_path)


@pytest.mark.asyncio
async def test_negative_invalid_nonce() -> None:
    """Verify decrypting too short payload (missing nonce) raises ValueError."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        temp_key_path = f.name
    try:
        vault = VaultManager(key_path=temp_key_path)
        await vault.initialize()

        short_b64 = base64.b64encode(os.urandom(8)).decode("utf-8")
        with pytest.raises(ValueError) as exc:
            vault._decrypt(short_b64)
        assert "too short" in str(exc.value)
    finally:
        os.remove(temp_key_path)


@pytest.mark.asyncio
async def test_negative_malformed_json_secrets() -> None:
    """Verify malformed JSON vault file raises initialization error."""
    with (
        tempfile.NamedTemporaryFile(delete=False) as f_key,
        tempfile.NamedTemporaryFile(delete=False) as f_secrets,
    ):
        temp_key = f_key.name
        temp_secrets = f_secrets.name

    try:
        with open(temp_secrets, "w") as f:
            f.write("invalid_json{malformed}")

        vault = VaultManager(key_path=temp_key, secrets_path=temp_secrets)
        with pytest.raises(JarvisSystemError) as exc_info:
            await vault.initialize()
        assert "Vault initialization failed" in exc_info.value.message
    finally:
        os.remove(temp_key)
        os.remove(temp_secrets)


@pytest.mark.asyncio
async def test_negative_unknown_secret_references() -> None:
    """Verify resolution logs errors and does not crash on unknown secrets."""
    with (
        tempfile.NamedTemporaryFile(delete=False) as f_key,
        tempfile.NamedTemporaryFile(delete=False) as f_secrets,
    ):
        temp_key = f_key.name
        temp_secrets = f_secrets.name

    try:
        vault = VaultManager(key_path=temp_key, secrets_path=temp_secrets)
        await vault.initialize()

        # Mock kernel and container
        kernel = Kernel()
        await kernel.initialize()
        kernel.container.register_singleton(VaultManager, vault)

        settings = Settings()
        settings.database.password = "vault://missing_secret"

        # Resolve should not raise exception but print log warning
        kernel._resolve_vault_secrets(settings)
        # Keeps original value
        assert settings.database.password == "vault://missing_secret"
    finally:
        os.remove(temp_key)
        os.remove(temp_secrets)
