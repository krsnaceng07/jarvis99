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

import os


class ConfigurationService:
    """Manages system configurations and secrets for the security package."""

    def __init__(self) -> None:
        """Initialize configurations resolving environment variables with safe defaults."""
        self.environment: str = os.getenv("JARVIS_SYSTEM_ENVIRONMENT", "production")
        self.jwt_secret: str = os.getenv(
            "JARVIS_SECURITY_JWT_SECRET",
            "super_secret_fallback_key_for_dev_only_use_environment_in_production_32bytes",
        )
        self.jwt_issuer: str = os.getenv("JARVIS_SECURITY_JWT_ISSUER", "jarvis_gateway")
        self.jwt_audience: str = os.getenv(
            "JARVIS_SECURITY_JWT_AUDIENCE", "jarvis_platform"
        )
        self.access_token_expire_minutes: int = int(
            os.getenv("JARVIS_SECURITY_ACCESS_TOKEN_EXPIRE_MINUTES", "15")
        )
        self.refresh_token_expire_days: int = int(
            os.getenv("JARVIS_SECURITY_REFRESH_TOKEN_EXPIRE_DAYS", "7")
        )
        self.bcrypt_cost: int = int(os.getenv("JARVIS_SECURITY_BCRYPT_COST", "12"))

        # Development seed administrator configurations
        self.admin_username: str = os.getenv("JARVIS_SECURITY_ADMIN_USERNAME", "admin")
        self.admin_password: str = os.getenv(
            "JARVIS_SECURITY_ADMIN_PASSWORD", "JarvisDev123!"
        )
