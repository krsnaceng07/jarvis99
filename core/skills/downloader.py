"""
PHASE: 18
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md (M4 Downloader)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from __future__ import annotations

import asyncio
import hashlib
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from core.exceptions import JarvisSkillError
from core.skills.download_dto import (
    DownloadedPackage,
    DownloadSourceKind,
    LocalPackageSkillSource,
    MarketplaceSkillSource,
    ResolvedPackageReference,
    SkillDownloadSource,
    TrustedRepositorySkillSource,
)

DEFAULT_MAX_PACKAGE_BYTES = 50 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 120.0
DEFAULT_STAGING_DIR = Path("/tmp/jarvis-skills-staging")


class SkillDownloadError(JarvisSkillError):
    """Downloader failures mapped to SKILL_D001–SKILL_D099."""


class MarketplaceCatalog(ABC):
    """Provider-agnostic marketplace lookup contract (docs/79 §11.1)."""

    @abstractmethod
    async def resolve_package(
        self, skill_id: str, version: Optional[str]
    ) -> ResolvedPackageReference:
        """Resolve marketplace skill ID to an internal fetch reference."""


class TrustedRepositoryCatalog(ABC):
    """Lookup contract for allowlisted enterprise/internal repositories."""

    @abstractmethod
    async def resolve_package(
        self,
        repository_id: str,
        skill_id: str,
        version: Optional[str],
    ) -> ResolvedPackageReference:
        """Resolve trusted repository coordinates to an internal fetch reference."""


class SkillDownloadSourceProvider(ABC):
    """Pluggable download source provider interface."""

    @property
    @abstractmethod
    def source_kind(self) -> DownloadSourceKind:
        """Source kind handled by this provider."""

    def supports(self, source: SkillDownloadSource) -> bool:
        """Return True when this provider can resolve the given source."""
        return source.kind == self.source_kind  # type: ignore[union-attr]

    @abstractmethod
    async def resolve(self, source: SkillDownloadSource) -> ResolvedPackageReference:
        """Resolve a typed source contract to an internal fetch reference."""


class MarketplaceDownloadProvider(SkillDownloadSourceProvider):
    """Resolve packages from marketplace skill IDs (no arbitrary URLs)."""

    def __init__(self, catalog: MarketplaceCatalog) -> None:
        self._catalog = catalog

    @property
    def source_kind(self) -> DownloadSourceKind:
        return "marketplace"

    async def resolve(self, source: SkillDownloadSource) -> ResolvedPackageReference:
        if not isinstance(source, MarketplaceSkillSource):
            raise SkillDownloadError(
                "SKILL_D003",
                "Marketplace provider received incompatible source type",
                {"source_kind": getattr(source, "kind", None)},
            )
        try:
            return await self._catalog.resolve_package(source.skill_id, source.version)
        except SkillDownloadError:
            raise
        except Exception as exc:  # pragma: no cover - defensive boundary
            raise SkillDownloadError(
                "SKILL_D005",
                "Marketplace source resolution failed",
                {"skill_id": source.skill_id, "error": str(exc)},
            ) from exc


class TrustedRepositoryDownloadProvider(SkillDownloadSourceProvider):
    """Resolve packages from allowlisted trusted repositories."""

    def __init__(
        self,
        catalog: TrustedRepositoryCatalog,
        allowed_repository_ids: frozenset[str],
    ) -> None:
        self._catalog = catalog
        self._allowed_repository_ids = allowed_repository_ids

    @property
    def source_kind(self) -> DownloadSourceKind:
        return "trusted_repository"

    async def resolve(self, source: SkillDownloadSource) -> ResolvedPackageReference:
        if not isinstance(source, TrustedRepositorySkillSource):
            raise SkillDownloadError(
                "SKILL_D003",
                "Trusted repository provider received incompatible source type",
                {"source_kind": getattr(source, "kind", None)},
            )
        if source.repository_id not in self._allowed_repository_ids:
            raise SkillDownloadError(
                "SKILL_D006",
                "Repository is not on the trusted allowlist",
                {"repository_id": source.repository_id},
            )
        try:
            return await self._catalog.resolve_package(
                source.repository_id,
                source.skill_id,
                source.version,
            )
        except SkillDownloadError:
            raise
        except Exception as exc:  # pragma: no cover - defensive boundary
            raise SkillDownloadError(
                "SKILL_D005",
                "Trusted repository source resolution failed",
                {
                    "repository_id": source.repository_id,
                    "skill_id": source.skill_id,
                    "error": str(exc),
                },
            ) from exc


class LocalPackageDownloadProvider(SkillDownloadSourceProvider):
    """Resolve packages from local filesystem archives."""

    @property
    def source_kind(self) -> DownloadSourceKind:
        return "local_package"

    async def resolve(self, source: SkillDownloadSource) -> ResolvedPackageReference:
        if not isinstance(source, LocalPackageSkillSource):
            raise SkillDownloadError(
                "SKILL_D003",
                "Local package provider received incompatible source type",
                {"source_kind": getattr(source, "kind", None)},
            )
        package_path = Path(source.package_path)
        if not package_path.is_file():
            raise SkillDownloadError(
                "SKILL_D007",
                "Local package archive not found",
                {"package_path": source.package_path},
            )
        checksum = _sha256_hex(package_path.read_bytes())
        skill_id = package_path.stem.split("-")[0] or package_path.stem
        version = "0.0.0"
        stem_parts = package_path.stem.rsplit("-", maxsplit=1)
        if len(stem_parts) == 2 and _looks_like_version(stem_parts[1]):
            skill_id = stem_parts[0]
            version = stem_parts[1]
        return ResolvedPackageReference(
            source_kind="local_package",
            skill_id=skill_id,
            version=version,
            expected_checksum=checksum,
            fetch_uri=str(package_path.resolve()),
        )


class SkillDownloader:
    """Download skill packages via pluggable typed source providers."""

    def __init__(
        self,
        providers: list[SkillDownloadSourceProvider],
        *,
        staging_dir: Path | None = None,
        max_package_bytes: int = DEFAULT_MAX_PACKAGE_BYTES,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._providers = {provider.source_kind: provider for provider in providers}
        self._staging_dir = staging_dir or _default_staging_dir()
        self._max_package_bytes = max_package_bytes
        self._timeout_seconds = timeout_seconds

    async def download(self, source: SkillDownloadSource) -> DownloadedPackage:
        """Resolve source, fetch archive, verify checksum, stage, and return."""
        provider = self._providers.get(source.kind)  # type: ignore[union-attr]
        if provider is None:
            raise SkillDownloadError(
                "SKILL_D003",
                "No download provider registered for source kind",
                {"source_kind": source.kind},  # type: ignore[union-attr]
            )

        reference = await provider.resolve(source)
        payload = await self._fetch_payload(reference)
        self._enforce_size_limit(payload)
        checksum = _sha256_hex(payload)
        if checksum != reference.expected_checksum:
            raise SkillDownloadError(
                "SKILL_D002",
                "Downloaded package checksum mismatch",
                {
                    "expected": reference.expected_checksum,
                    "actual": checksum,
                    "skill_id": reference.skill_id,
                },
            )

        package_path = await self._stage_package(reference, payload)
        return DownloadedPackage(
            skill_id=reference.skill_id,
            version=reference.version,
            source_kind=reference.source_kind,
            package_path=str(package_path),
            checksum=checksum,
            size_bytes=len(payload),
        )

    async def _fetch_payload(self, reference: ResolvedPackageReference) -> bytes:
        uri = reference.fetch_uri
        if uri.startswith(("http://", "https://")):
            try:
                return await asyncio.wait_for(
                    asyncio.to_thread(_http_get, uri),
                    timeout=self._timeout_seconds,
                )
            except TimeoutError as exc:
                raise SkillDownloadError(
                    "SKILL_D001",
                    "Download timed out",
                    {"fetch_uri": uri},
                ) from exc
            except urllib.error.URLError as exc:
                raise SkillDownloadError(
                    "SKILL_D008",
                    "Package fetch failed",
                    {"fetch_uri": uri, "error": str(exc.reason)},
                ) from exc
        return await asyncio.to_thread(Path(uri).read_bytes)

    def _enforce_size_limit(self, payload: bytes) -> None:
        if len(payload) > self._max_package_bytes:
            raise SkillDownloadError(
                "SKILL_D004",
                "Downloaded package exceeds size limit",
                {
                    "size_bytes": len(payload),
                    "max_package_bytes": self._max_package_bytes,
                },
            )

    async def _stage_package(
        self, reference: ResolvedPackageReference, payload: bytes
    ) -> Path:
        self._staging_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{reference.skill_id}-{reference.version}.zip"
        package_path = self._staging_dir / filename
        await asyncio.to_thread(package_path.write_bytes, payload)
        return package_path


def _default_staging_dir() -> Path:
    import sys
    import tempfile

    if sys.platform == "win32":
        return Path(tempfile.gettempdir()) / "jarvis-skills-staging"
    return DEFAULT_STAGING_DIR


def _sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _looks_like_version(value: str) -> bool:
    parts = value.split(".")
    return len(parts) == 3 and all(part.isdigit() for part in parts)


def _http_get(url: str) -> bytes:
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
        return response.read()
