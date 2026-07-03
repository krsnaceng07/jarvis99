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

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import jwt

from core.security.configuration_service import ConfigurationService


class JWTService:
    """Handles JWT generation, parsing, and verification using HS256."""

    def __init__(self, config: ConfigurationService) -> None:
        """Initialize the JWT service with system configurations."""
        self.config = config

    def sign_token(
        self,
        user_id: str,
        username: str,
        roles: List[str],
        permissions: List[str],
        jti: str,
    ) -> str:
        """Sign a new access JWT containing standard claims and credentials."""
        now = datetime.now(timezone.utc)
        expire = now + timedelta(minutes=self.config.access_token_expire_minutes)

        payload = {
            "sub": user_id,
            "username": username,
            "roles": roles,
            "permissions": permissions,
            "iat": int(now.timestamp()),
            "exp": int(expire.timestamp()),
            "jti": jti,
            "iss": self.config.jwt_issuer,
            "aud": self.config.jwt_audience,
        }

        return jwt.encode(payload, self.config.jwt_secret, algorithm="HS256")

    def verify_token(self, token: str) -> Dict[str, Any]:
        """Verify the signature and claims of an access token.

        Raises jwt.PyJWTError if invalid or expired.
        """
        payload = jwt.decode(
            token,
            self.config.jwt_secret,
            algorithms=["HS256"],
            audience=self.config.jwt_audience,
            issuer=self.config.jwt_issuer,
        )
        return payload

    def decode_token_unverified(self, token: str) -> Dict[str, Any]:
        """Decode a token without verifying its signature (unsafe lookup helper)."""
        return jwt.decode(token, options={"verify_signature": False})
