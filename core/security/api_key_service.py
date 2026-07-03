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

import hashlib
import secrets
from typing import Tuple


class ApiKeyService:
    """Manages secure generation and verification of programmatic API keys."""

    def generate_api_key(self, prefix: str = "jvs_live_") -> Tuple[str, str]:
        """Generate a random programmatic API Key.

        Returns (raw_key, hashed_key) where:
        - raw_key starts with the prefix followed by 64 hex characters (32-bytes entropy).
        - hashed_key is the SHA-256 hash of raw_key.
        """
        entropy = secrets.token_hex(32)
        raw_key = f"{prefix}{entropy}"
        hashed_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        return raw_key, hashed_key

    def verify_api_key(self, raw_key: str, hashed_key: str) -> bool:
        """Verify if a raw key matches a stored SHA-256 hash.

        Employs constant-time comparison to prevent timing attacks.
        """
        try:
            computed = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
            # Perform constant-time check
            return secrets.compare_digest(computed, hashed_key)
        except Exception:
            return False
