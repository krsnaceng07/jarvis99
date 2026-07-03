"""Phase 18 M4 downloader tests (source resolution + fetch + checksum only)."""

import hashlib
import importlib
from pathlib import Path
from typing import Optional

import pytest

from core.skills.download_dto import (
    LocalPackageSkillSource,
    MarketplaceSkillSource,
    ResolvedPackageReference,
    TrustedRepositorySkillSource,
)
from core.skills.downloader import (
    LocalPackageDownloadProvider,
    MarketplaceCatalog,
    MarketplaceDownloadProvider,
    SkillDownloader,
    SkillDownloadError,
    TrustedRepositoryCatalog,
    TrustedRepositoryDownloadProvider,
)


def _checksum(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


@pytest.mark.asyncio
async def test_local_package_download_success(tmp_path: Path) -> None:
    payload = b"zip-bytes-for-youtube-skill"
    package_file = tmp_path / "youtube-1.0.0.zip"
    package_file.write_bytes(payload)
    staging_dir = tmp_path / "staging"

    downloader = SkillDownloader(
        [LocalPackageDownloadProvider()],
        staging_dir=staging_dir,
    )
    result = await downloader.download(
        LocalPackageSkillSource(package_path=str(package_file))
    )

    assert result.skill_id == "youtube"
    assert result.version == "1.0.0"
    assert result.source_kind == "local_package"
    assert result.checksum == _checksum(payload)
    assert Path(result.package_path).exists()
    assert Path(result.package_path).read_bytes() == payload


@pytest.mark.asyncio
async def test_checksum_mismatch_raises_d002(tmp_path: Path) -> None:
    payload = b"valid-package"
    package_file = tmp_path / "github-2.0.0.zip"
    package_file.write_bytes(payload)

    class _BadLocalProvider(LocalPackageDownloadProvider):
        async def resolve(self, source):  # type: ignore[no-untyped-def]
            reference = await super().resolve(source)
            return reference.model_copy(update={"expected_checksum": "0" * 64})

    downloader = SkillDownloader(
        [_BadLocalProvider()],
        staging_dir=tmp_path / "staging",
    )
    with pytest.raises(SkillDownloadError) as exc:
        await downloader.download(
            LocalPackageSkillSource(package_path=str(package_file))
        )
    assert exc.value.code == "SKILL_D002"


@pytest.mark.asyncio
async def test_package_too_large_raises_d004(tmp_path: Path) -> None:
    payload = b"x" * 32
    package_file = tmp_path / "big-1.0.0.zip"
    package_file.write_bytes(payload)

    downloader = SkillDownloader(
        [LocalPackageDownloadProvider()],
        staging_dir=tmp_path / "staging",
        max_package_bytes=16,
    )
    with pytest.raises(SkillDownloadError) as exc:
        await downloader.download(
            LocalPackageSkillSource(package_path=str(package_file))
        )
    assert exc.value.code == "SKILL_D004"


@pytest.mark.asyncio
async def test_marketplace_provider_resolves_via_catalog(tmp_path: Path) -> None:
    payload = b"marketplace-package"
    package_file = tmp_path / "notion-1.2.3.zip"
    package_file.write_bytes(payload)

    class _PathMarketplaceCatalog(MarketplaceCatalog):
        async def resolve_package(
            self, skill_id: str, version: Optional[str]
        ) -> ResolvedPackageReference:
            return ResolvedPackageReference(
                source_kind="marketplace",
                skill_id=skill_id,
                version=version or "1.2.3",
                expected_checksum=_checksum(payload),
                fetch_uri=str(package_file),
            )

    downloader = SkillDownloader(
        [MarketplaceDownloadProvider(_PathMarketplaceCatalog())],
        staging_dir=tmp_path / "staging",
    )
    result = await downloader.download(
        MarketplaceSkillSource(skill_id="notion", version="1.2.3")
    )
    assert result.skill_id == "notion"
    assert result.source_kind == "marketplace"


@pytest.mark.asyncio
async def test_trusted_repository_rejects_unlisted_repo(tmp_path: Path) -> None:
    class _EmptyCatalog(TrustedRepositoryCatalog):
        async def resolve_package(
            self,
            repository_id: str,
            skill_id: str,
            version: Optional[str],
        ) -> ResolvedPackageReference:
            raise AssertionError("catalog should not be called for untrusted repo")

    downloader = SkillDownloader(
        [
            TrustedRepositoryDownloadProvider(
                _EmptyCatalog(),
                allowed_repository_ids=frozenset({"jarvis-official"}),
            )
        ],
        staging_dir=tmp_path / "staging",
    )
    with pytest.raises(SkillDownloadError) as exc:
        await downloader.download(
            TrustedRepositorySkillSource(
                repository_id="random-repo",
                skill_id="slack",
            )
        )
    assert exc.value.code == "SKILL_D006"


@pytest.mark.asyncio
async def test_missing_provider_raises_d003(tmp_path: Path) -> None:
    downloader = SkillDownloader([], staging_dir=tmp_path / "staging")
    with pytest.raises(SkillDownloadError) as exc:
        await downloader.download(MarketplaceSkillSource(skill_id="youtube"))
    assert exc.value.code == "SKILL_D003"


@pytest.mark.asyncio
async def test_local_package_missing_raises_d007(tmp_path: Path) -> None:
    downloader = SkillDownloader(
        [LocalPackageDownloadProvider()],
        staging_dir=tmp_path / "staging",
    )
    with pytest.raises(SkillDownloadError) as exc:
        await downloader.download(
            LocalPackageSkillSource(package_path=str(tmp_path / "missing.zip"))
        )
    assert exc.value.code == "SKILL_D007"


def test_downloader_has_no_forbidden_dependencies() -> None:
    module = importlib.import_module("core.skills.downloader")
    module_path = module.__file__
    assert module_path is not None
    source = open(module_path, encoding="utf-8").read()
    for forbidden in (
        "SkillRepository",
        "SkillRegistry",
        "SkillValidator",
        "sqlalchemy",
    ):
        assert forbidden not in source
