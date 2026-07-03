"""Phase 18 M7 SkillSigner contract tests (pure, no I/O)."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.skills.signer import CertificateChain, SkillSigner
from core.tools.security import PermissionGatekeeper


def _make_skill_dir(tmp_path: Path, files: dict[str, str] | None = None) -> Path:
    """Create a minimal skill directory with deterministic content."""
    skill_dir = tmp_path / "test_skill"
    skill_dir.mkdir(exist_ok=True)
    content = files or {"main.py": "print('hello')", "README.md": "test skill"}
    for name, body in content.items():
        (skill_dir / name).write_text(body)
    return skill_dir


def _sign_dir(skill_dir: Path) -> str:
    """Compute the canonical SHA-256 signature for a skill directory."""
    return PermissionGatekeeper.calculate_directory_hash(str(skill_dir))


def _valid_cert(
    root: str = "jarvis-root-v1",
    pub: str = "publisher-1",
    issued: datetime | None = None,
    expires: datetime | None = None,
    revoked: bool = False,
) -> CertificateChain:
    now = datetime.now(timezone.utc)
    return CertificateChain(
        root_fingerprint=root,
        publisher_fingerprint=pub,
        issued_at=issued or (now - timedelta(days=1)),
        expires_at=expires or (now + timedelta(days=365)),
        revoked=revoked,
    )


class TestValidSignature:
    def test_valid_signature_passes(self, tmp_path: Path) -> None:
        skill_dir = _make_skill_dir(tmp_path)
        sig = _sign_dir(skill_dir)
        signer = SkillSigner()

        result = signer.verify(skill_dir, sig)

        assert result.decision == "VALID"
        assert result.directory_hash == sig

    def test_valid_signature_with_valid_cert(self, tmp_path: Path) -> None:
        skill_dir = _make_skill_dir(tmp_path)
        sig = _sign_dir(skill_dir)
        signer = SkillSigner()
        cert = _valid_cert()

        result = signer.verify(skill_dir, sig, publisher_certificate=cert)

        assert result.decision == "VALID"


class TestTamperedPackage:
    def test_tampered_file_detected(self, tmp_path: Path) -> None:
        skill_dir = _make_skill_dir(tmp_path)
        sig = _sign_dir(skill_dir)
        signer = SkillSigner()

        # Tamper with a file after signing
        (skill_dir / "main.py").write_text("print('tampered')")

        result = signer.verify(skill_dir, sig)

        assert result.decision == "TAMPERED"
        assert result.directory_hash != sig

    def test_extra_file_detected(self, tmp_path: Path) -> None:
        skill_dir = _make_skill_dir(tmp_path)
        sig = _sign_dir(skill_dir)
        signer = SkillSigner()

        # Add extra file after signing
        (skill_dir / "backdoor.py").write_text("import os; os.system('rm -rf /')")

        result = signer.verify(skill_dir, sig)

        assert result.decision == "TAMPERED"

    def test_deleted_file_detected(self, tmp_path: Path) -> None:
        skill_dir = _make_skill_dir(tmp_path)
        sig = _sign_dir(skill_dir)
        signer = SkillSigner()

        # Delete a file after signing
        (skill_dir / "README.md").unlink()

        result = signer.verify(skill_dir, sig)

        assert result.decision == "TAMPERED"


class TestUnsignedPackage:
    def test_empty_signature_rejected(self, tmp_path: Path) -> None:
        skill_dir = _make_skill_dir(tmp_path)
        signer = SkillSigner()

        result = signer.verify(skill_dir, "")

        assert result.decision == "UNSIGNED"
        assert "unsigned" in result.message.lower()


class TestCertificateChain:
    def test_expired_cert_rejected(self, tmp_path: Path) -> None:
        skill_dir = _make_skill_dir(tmp_path)
        sig = _sign_dir(skill_dir)
        signer = SkillSigner()

        expired_cert = _valid_cert(
            issued=datetime(2020, 1, 1, tzinfo=timezone.utc),
            expires=datetime(2020, 12, 31, tzinfo=timezone.utc),
        )

        result = signer.verify(skill_dir, sig, publisher_certificate=expired_cert)

        assert result.decision == "EXPIRED"
        assert "expired" in result.message.lower()

    def test_not_yet_valid_cert_rejected(self, tmp_path: Path) -> None:
        skill_dir = _make_skill_dir(tmp_path)
        sig = _sign_dir(skill_dir)
        signer = SkillSigner()

        future_cert = _valid_cert(
            issued=datetime(2030, 1, 1, tzinfo=timezone.utc),
            expires=datetime(2035, 12, 31, tzinfo=timezone.utc),
        )

        result = signer.verify(skill_dir, sig, publisher_certificate=future_cert)

        assert result.decision == "EXPIRED"

    def test_revoked_cert_rejected(self, tmp_path: Path) -> None:
        skill_dir = _make_skill_dir(tmp_path)
        sig = _sign_dir(skill_dir)
        signer = SkillSigner()

        revoked_cert = _valid_cert(revoked=True)

        result = signer.verify(skill_dir, sig, publisher_certificate=revoked_cert)

        assert result.decision == "CHAIN_INVALID"
        assert "revoked" in result.message.lower()

    def test_wrong_root_fingerprint_rejected(self, tmp_path: Path) -> None:
        skill_dir = _make_skill_dir(tmp_path)
        sig = _sign_dir(skill_dir)
        signer = SkillSigner(trusted_root_fingerprint="jarvis-root-v1")

        wrong_root_cert = _valid_cert(root="attacker-root-v1")

        result = signer.verify(skill_dir, sig, publisher_certificate=wrong_root_cert)

        assert result.decision == "CHAIN_INVALID"
        assert "root" in result.message.lower()


class TestNoCertificate:
    def test_no_cert_skips_chain_validation(self, tmp_path: Path) -> None:
        skill_dir = _make_skill_dir(tmp_path)
        sig = _sign_dir(skill_dir)
        signer = SkillSigner()

        # No certificate — only hash comparison
        result = signer.verify(skill_dir, sig, publisher_certificate=None)

        assert result.decision == "VALID"


class TestSignerModule:
    def test_signer_has_no_forbidden_dependencies(self) -> None:
        """SkillSigner must NOT depend on core.skills.repository, registry, or installer."""
        import ast
        from pathlib import Path

        source = Path("core/skills/signer.py").read_text()
        tree = ast.parse(source)

        forbidden = {"repository", "registry", "installer", "downloader", "sandbox"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                parts = set(node.module.split("."))
                overlap = parts & forbidden
                assert not overlap, f"Forbidden dependency: {node.module}"
