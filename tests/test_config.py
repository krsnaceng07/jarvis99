"""JARVIS OS - Configuration and Security Vault Unit Tests.

Verifies YAML config loading, Pydantic type checking, env overrides, and vault cryptors.
"""

import os
import tempfile

import pytest

from core.config import Settings
from core.exceptions import JarvisSystemError
from core.security.vault import VaultManager


def test_settings_load_defaults() -> None:
    """Verify settings fallback to correct defaults when no file is present."""
    settings = Settings.load_settings()
    assert settings.system.environment == "production"
    assert not settings.system.debug
    assert settings.database.host == "localhost"
    assert settings.redis.port == 6379


def test_settings_load_yaml_success() -> None:
    """Verify settings correctly parse matching YAML config file."""
    yaml_content = """
system:
  environment: "development"
  debug: true
  log_level: "DEBUG"
database:
  host: "db-server"
  port: 9999
  name: "test_db"
  username: "test_user"
"""
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        temp_name = f.name

    try:
        settings = Settings.load_settings(yaml_path=temp_name)
        assert settings.system.environment == "development"
        assert settings.system.debug
        assert settings.database.host == "db-server"
        assert settings.database.port == 9999
    finally:
        os.remove(temp_name)


def test_settings_load_yaml_missing_fail() -> None:
    """Verify settings fail if configuration YAML path is not found."""
    with pytest.raises(JarvisSystemError) as exc_info:
        Settings.load_settings(yaml_path="non_existent_config_file_xyz.yaml")
    assert exc_info.value.code == "SYSTEM_001"
    assert "Configuration file not found" in exc_info.value.message


def test_settings_load_yaml_invalid_type_fail() -> None:
    """Verify settings fail when type conversions fail."""
    yaml_content = """
database:
  port: "invalid_integer_port_value"
"""
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        temp_name = f.name

    try:
        with pytest.raises(JarvisSystemError) as exc_info:
            Settings.load_settings(yaml_path=temp_name)
        assert exc_info.value.code == "SYSTEM_001"
        assert "validation failed" in exc_info.value.message
    finally:
        os.remove(temp_name)


def test_settings_env_override() -> None:
    """Verify env variables override configuration parameters correctly."""
    os.environ["JARVIS_SYSTEM__ENVIRONMENT"] = "staging"
    os.environ["JARVIS_DATABASE__HOST"] = "env-db-host"
    try:
        settings = Settings.load_settings()
        assert settings.system.environment == "staging"
        assert settings.database.host == "env-db-host"
    finally:
        del os.environ["JARVIS_SYSTEM__ENVIRONMENT"]
        del os.environ["JARVIS_DATABASE__HOST"]


@pytest.mark.asyncio
async def test_vault_manager_encryption_decryption() -> None:
    """Verify VaultManager initializes, encrypts, and decrypts secrets correctly."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        temp_key_path = f.name

    try:
        # Create vault and initialize (should generate master.key)
        vault = VaultManager(key_path=temp_key_path)
        await vault.initialize()

        # Set secret
        secret_key = "test_api_key"
        secret_val = "sk-1234567890abcdef"
        vault.set_secret(secret_key, secret_val)

        # Get secret
        decrypted = vault.get_secret(secret_key)
        assert decrypted == secret_val

        # Get missing secret fails
        with pytest.raises(JarvisSystemError) as exc_info:
            vault.get_secret("non_existent_secret")
        assert exc_info.value.code == "SYSTEM_001"
        assert "not found" in exc_info.value.message

    finally:
        os.remove(temp_key_path)


@pytest.mark.asyncio
async def test_vault_manager_uninitialized_fail() -> None:
    """Verify operations on uninitialized vault fail."""
    vault = VaultManager(key_path="some_path.key")
    with pytest.raises(JarvisSystemError):
        vault.get_secret("secret")
    with pytest.raises(JarvisSystemError):
        vault.set_secret("secret", "value")


@pytest.mark.asyncio
async def test_vault_manager_failures() -> None:
    """Verify VaultManager handles directory and decryption errors correctly."""
    # 1. Directory creation failure
    # We use an invalid path with forbidden characters on Windows (like NUL byte or illegal chars) to force directory creation to fail
    vault = VaultManager(key_path="\x00invalid/dir/master.key")
    with pytest.raises(JarvisSystemError) as exc_info:
        await vault.initialize()
    assert exc_info.value.code == "SYSTEM_001"
    assert "Vault initialization failed" in exc_info.value.message

    # 2. Decryption ValueError on corrupt / short values
    with tempfile.NamedTemporaryFile(delete=False) as f:
        temp_key_path = f.name
    try:
        vault2 = VaultManager(key_path=temp_key_path)
        await vault2.initialize()

        # Directly inject a corrupt ciphertext string
        vault2._secrets["corrupt_key"] = "short"
        with pytest.raises(JarvisSystemError) as exc_info:
            vault2.get_secret("corrupt_key")
        assert exc_info.value.code == "SYSTEM_999"
        assert "Failed to decrypt" in exc_info.value.message
    finally:
        os.remove(temp_key_path)
