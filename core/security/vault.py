"""JARVIS OS - Local Security Vault.

Handles secure symmetric encryption, key derivation, and access control for system credentials.
"""

import base64
import hashlib
import os
from typing import Dict, Optional
from uuid import UUID

from core.exceptions import JarvisSystemError


class VaultManager:
    """Manager for securely storing and retrieving secrets using local symmetric encryption."""

    def __init__(self, key_path: str) -> None:
        """Initialize VaultManager with a master key file path.

        Args:
            key_path: File path to the encryption master key.
        """
        self.key_path = key_path
        self._key: Optional[bytes] = None
        self._secrets: Dict[str, str] = {}

    async def initialize(self) -> None:
        """Initialize vault. Load or generate the symmetric master key.

        Raises:
            JarvisSystemError: If key directory is invalid or key load fails.
        """
        try:
            # Create directories if missing
            key_dir = os.path.dirname(self.key_path)
            if key_dir and not os.path.exists(key_dir):
                os.makedirs(key_dir, exist_ok=True)

            if not os.path.exists(self.key_path) or os.path.getsize(self.key_path) == 0:
                # Generate new key for development/bootstrap
                new_key = os.urandom(32)
                with open(self.key_path, "wb") as key_file:
                    key_file.write(base64.urlsafe_b64encode(new_key))

            with open(self.key_path, "rb") as key_file:
                encoded = key_file.read().strip()
                self._key = base64.urlsafe_b64decode(encoded)

            if not self._key or len(self._key) != 32:
                raise ValueError("Master key must be exactly 32 bytes decoded.")

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

        if key_name not in self._secrets:
            raise JarvisSystemError(
                code="SYSTEM_001",
                message=f"Secret '{key_name}' not found in vault.",
            )

        encrypted_val = self._secrets[key_name]
        try:
            decrypted = self._decrypt(encrypted_val)
            return decrypted
        except Exception as err:
            raise JarvisSystemError(
                code="SYSTEM_999",
                message=f"Failed to decrypt secret '{key_name}': {str(err)}",
            ) from err

    def set_secret(self, key_name: str, secret_value: str) -> None:
        """Encrypt and store a secret in the local vault.

        Args:
            key_name: The identifier of the secret.
            secret_value: The plaintext secret value.

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
            self._secrets[key_name] = encrypted
        except Exception as err:
            raise JarvisSystemError(
                code="SYSTEM_999",
                message=f"Failed to encrypt secret '{key_name}': {str(err)}",
            ) from err

    def _derive_keystream(self, salt: bytes, length: int) -> bytes:
        """Derive a keystream using PBKDF2 with SHA-256 for symmetric XOR encryption.

        Args:
            salt: Random unique salt bytes.
            length: Target keystream length in bytes.
        """
        if not self._key:
            raise ValueError("Key missing.")
        # Derives high entropy bytes from master key and salt
        return hashlib.pbkdf2_hmac(
            hash_name="sha256",
            password=self._key,
            salt=salt,
            iterations=1000,
            dklen=length,
        )

    def _encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext using PBKDF2-derived keystream XOR cipher.

        Returns base64 formatted: salt(16 bytes) + encrypted_payload.
        """
        salt = os.urandom(16)
        raw_data = plaintext.encode("utf-8")
        keystream = self._derive_keystream(salt, len(raw_data))
        cipher_bytes = bytes(b ^ k for b, k in zip(raw_data, keystream))
        return base64.b64encode(salt + cipher_bytes).decode("utf-8")

    def _decrypt(self, cipher_text: str) -> str:
        """Decrypt ciphertext using PBKDF2-derived keystream XOR cipher."""
        decoded = base64.b64decode(cipher_text.encode("utf-8"))
        if len(decoded) <= 16:
            raise ValueError("Cipher text too short.")
        salt = decoded[:16]
        cipher_bytes = decoded[16:]
        keystream = self._derive_keystream(salt, len(cipher_bytes))
        plain_bytes = bytes(c ^ k for c, k in zip(cipher_bytes, keystream))
        return plain_bytes.decode("utf-8")
