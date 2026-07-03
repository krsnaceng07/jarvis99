"""
PHASE: 17
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/78_PHASE_17_AUTHENTICATION_AUTHORIZATION_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/721908f6-e992-4e3d-9eca-2fca584e321e/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import bcrypt


class PasswordService:
    """Handles secure password hashing and verification using Bcrypt."""

    def __init__(self, cost_factor: int = 12) -> None:
        """Initialize the password service with a configurable cost factor (default 12)."""
        self.cost_factor = cost_factor

    def hash_password(self, password: str) -> str:
        """Hash a plaintext password using Bcrypt with the configured cost factor.

        Plaintext passwords are never stored or logged.
        """
        pw_bytes = password.encode("utf-8")
        salt = bcrypt.gensalt(rounds=self.cost_factor)
        hashed_bytes = bcrypt.hashpw(pw_bytes, salt)
        return hashed_bytes.decode("utf-8")

    def verify_password(self, password: str, hashed: str) -> bool:
        """Verify a plaintext password against a stored Bcrypt hash.

        Returns False and fails closed if verification fails or the hash is corrupted/invalid.
        """
        try:
            pw_bytes = password.encode("utf-8")
            hashed_bytes = hashed.encode("utf-8")
            return bcrypt.checkpw(pw_bytes, hashed_bytes)
        except Exception:
            # Fail closed on any decryption, encoding, or format mismatch exceptions
            return False
