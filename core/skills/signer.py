"""
PHASE: 41
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/103_PHASE_41_CAPABILITY_REGISTRY_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/8e27d67d-09cc-4e93-9e3e-d5a4bb653dd9/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from core.tools.security import PermissionGatekeeper

SignerDecision = Literal["VALID", "TAMPERED", "UNSIGNED", "EXPIRED", "CHAIN_INVALID"]


@dataclass(frozen=True)
class SignatureVerification:
    """Structured result of signature verification."""

    decision: SignerDecision
    directory_hash: str
    expected_signature: str
    message: str


@dataclass(frozen=True)
class CertificateChain:
    """Represents a certificate chain for trust validation."""

    root_fingerprint: str
    publisher_fingerprint: str
    issued_at: datetime
    expires_at: datetime
    revoked: bool = False


class SkillSigner:
    """
    Verifies skill package signatures via PermissionGatekeeper.calculate_directory_hash()
    and validates certificate chain per spec §14.1.

    Responsibility: Signature verification ONLY.
    - No database writes
    - No installation
    - No permission evaluation
    """

    def __init__(self, trusted_root_fingerprint: str | None = None) -> None:
        self._trusted_root = trusted_root_fingerprint or "jarvis-root-v1"

    def verify(
        self,
        skill_dir: Path,
        expected_signature: str,
        publisher_certificate: CertificateChain | None = None,
    ) -> SignatureVerification:
        """
        Verify skill package integrity.

        Validation sequence (spec §14.1):
        1. Recompute directory hash via PermissionGatekeeper.calculate_directory_hash().
        2. Compare against expected_signature.
        3. If publisher_certificate provided, validate chain.
        4. Return structured result.
        """
        if not expected_signature:
            return SignatureVerification(
                decision="UNSIGNED",
                directory_hash="",
                expected_signature="",
                message="Package has no signature. Unsigned skills cannot be installed.",
            )

        directory_hash = PermissionGatekeeper.calculate_directory_hash(str(skill_dir))

        if directory_hash != expected_signature:
            return SignatureVerification(
                decision="TAMPERED",
                directory_hash=directory_hash,
                expected_signature=expected_signature,
                message="Signature mismatch. Package files may have been modified.",
            )

        if publisher_certificate is not None:
            chain_result = self._validate_chain(publisher_certificate)
            if chain_result.decision != "VALID":
                return SignatureVerification(
                    decision=chain_result.decision,
                    directory_hash=directory_hash,
                    expected_signature=expected_signature,
                    message=chain_result.message,
                )

        return SignatureVerification(
            decision="VALID",
            directory_hash=directory_hash,
            expected_signature=expected_signature,
            message="Signature verified successfully.",
        )

    def _validate_chain(self, cert: CertificateChain) -> SignatureVerification:
        """Validate certificate chain per spec §14.1."""
        now = datetime.now(timezone.utc)

        if cert.revoked:
            return SignatureVerification(
                decision="CHAIN_INVALID",
                directory_hash="",
                expected_signature="",
                message="Publisher certificate has been revoked.",
            )

        if now < cert.issued_at or now > cert.expires_at:
            return SignatureVerification(
                decision="EXPIRED",
                directory_hash="",
                expected_signature="",
                message="Publisher certificate is expired or not yet valid.",
            )

        if cert.root_fingerprint != self._trusted_root:
            return SignatureVerification(
                decision="CHAIN_INVALID",
                directory_hash="",
                expected_signature="",
                message="Root certificate fingerprint does not match trusted root.",
            )

        return SignatureVerification(
            decision="VALID",
            directory_hash="",
            expected_signature="",
            message="Certificate chain validated.",
        )
