"""Phase 18 M5 sandbox tests (extract + run + structured result only)."""

import importlib
import zipfile
from pathlib import Path

import pytest

from core.skills.download_dto import DownloadedPackage
from core.skills.dto import (
    SkillCapability,
    SkillCompatibility,
    SkillDependency,
    SkillLimits,
    SkillManifest,
)
from core.skills.sandbox import (
    ProcessSandboxRunner,
    SandboxTestRunner,
    SkillSandboxError,
)
from core.skills.sandbox_dto import SandboxResult


def _manifest(
    *,
    isolation: str = "container",
    memory: str = "256MB",
    cpu: str = "0.5",
    timeout: int = 30,
) -> SkillManifest:
    return SkillManifest(
        id="youtube",
        name="YouTube Skill",
        version="1.0.0",
        author="jarvis",
        description="skill",
        permissions=["network"],
        dependencies=[SkillDependency(skill="core_search", version="1.0.0")],
        signature="x" * 32,
        checksum="a" * 64,
        jarvis_api_version="1.0",
        min_runtime_version="1.0",
        trust_level="OFFICIAL",
        capabilities=[
            SkillCapability(key="youtube.video.search", description="search videos")
        ],
        compatibility=SkillCompatibility(
            platforms=["windows"],
            architectures=["x64"],
            python="3.14.0",
            jarvis_runtime="1.0.0",
        ),
        limits=SkillLimits(
            memory=memory,
            cpu=cpu,
            timeout=timeout,
            network=False,
            filesystem="sandbox",
        ),
        isolation=isolation,  # type: ignore[arg-type]
    )


def _create_skill_zip(
    base: Path, script: str, *, name: str = "youtube-1.0.0.zip"
) -> Path:
    package_path = base / name
    tests_path = base / "tests"
    tests_path.mkdir(exist_ok=True)
    test_file = tests_path / "test_main.py"
    test_file.write_text(script, encoding="utf-8")
    with zipfile.ZipFile(package_path, "w") as archive:
        archive.write(test_file, "tests/test_main.py")
    return package_path


def _downloaded_package(path: Path) -> DownloadedPackage:
    return DownloadedPackage(
        skill_id="youtube",
        version="1.0.0",
        source_kind="local_package",
        package_path=str(path),
        checksum="a" * 64,
        size_bytes=max(path.stat().st_size, 1),
    )


@pytest.mark.asyncio
async def test_sandbox_runner_success(tmp_path: Path) -> None:
    package_path = _create_skill_zip(tmp_path, "print('ok')\n")
    service = SandboxTestRunner(
        runners=[ProcessSandboxRunner()],
        enforce_container_isolation=False,
    )

    result = await service.run(
        _downloaded_package(package_path), _manifest(isolation="process")
    )
    assert result.status == "PASSED"
    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_sandbox_runner_failure_returns_structured_result(tmp_path: Path) -> None:
    package_path = _create_skill_zip(tmp_path, "raise SystemExit(3)\n")
    service = SandboxTestRunner(
        runners=[ProcessSandboxRunner()],
        enforce_container_isolation=False,
    )

    result = await service.run(
        _downloaded_package(package_path), _manifest(isolation="process")
    )
    assert result.status == "FAILED"
    assert result.exit_code == 3
    assert isinstance(result, SandboxResult)


@pytest.mark.asyncio
async def test_missing_test_main_raises(tmp_path: Path) -> None:
    package_path = tmp_path / "youtube-1.0.0.zip"
    with zipfile.ZipFile(package_path, "w"):
        pass

    service = SandboxTestRunner(
        runners=[ProcessSandboxRunner()],
        enforce_container_isolation=False,
    )
    with pytest.raises(SkillSandboxError) as exc:
        await service.run(
            _downloaded_package(package_path), _manifest(isolation="process")
        )
    assert "SKILL_SB003" in str(exc.value)


@pytest.mark.asyncio
async def test_limit_violation_rejected_before_execution(tmp_path: Path) -> None:
    package_path = _create_skill_zip(tmp_path, "print('ok')\n")
    service = SandboxTestRunner(
        runners=[ProcessSandboxRunner()],
        enforce_container_isolation=False,
    )
    with pytest.raises(SkillSandboxError) as exc:
        await service.run(
            _downloaded_package(package_path),
            _manifest(isolation="process", memory="1024MB"),
        )
    assert "SKILL_SB002" in str(exc.value)


@pytest.mark.asyncio
async def test_phase18_enforces_container_isolation(tmp_path: Path) -> None:
    package_path = _create_skill_zip(tmp_path, "print('ok')\n")
    service = SandboxTestRunner(runners=[ProcessSandboxRunner()])
    with pytest.raises(SkillSandboxError) as exc:
        await service.run(
            _downloaded_package(package_path), _manifest(isolation="process")
        )
    assert "SKILL_SB004" in str(exc.value)


def test_sandbox_module_has_no_forbidden_dependencies() -> None:
    module = importlib.import_module("core.skills.sandbox")
    module_path = module.__file__
    assert module_path is not None
    source = Path(module_path).read_text(encoding="utf-8")
    for forbidden in (
        "SkillRepository",
        "SkillRegistry",
        "SkillInstaller",
        "sqlalchemy",
    ):
        assert forbidden not in source


# ---------------------------------------------------------------------------
# CR-004 polish tests (3.2 narrow exception, 3.7 default-by-availability)
# ---------------------------------------------------------------------------


def test_docker_is_available_narrows_exception_classes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CR-004 §3.2: probe splits ImportError from OSError / ConnectionError.

    The pre-fix probe caught ``Exception`` broadly, which silently masked
    programmer errors (AttributeError, TypeError) as "Docker unavailable".
    The fix splits the two ``try`` blocks so:
      * ``(ImportError, ModuleNotFoundError)`` → returns False (SDK missing)
      * ``(OSError, ConnectionError)`` → returns False (daemon unreachable)
      * Anything else (programmer error in the probe) → propagates

    This test exercises the third branch by monkeypatching
    ``docker.from_env`` to raise ``AttributeError`` (a programmer error
    in the probe), which must now propagate instead of being swallowed.
    """
    from core.skills import sandbox as sandbox_mod

    # Simulate a programmer error in the probe by raising AttributeError
    # from inside the import-ok branch. The fix must let this propagate.
    class _BoomDocker:
        @staticmethod
        def from_env() -> None:
            raise AttributeError("simulated probe bug")

    monkeypatch.setitem(__import__("sys").modules, "docker", _BoomDocker)
    with pytest.raises(AttributeError, match="simulated probe bug"):
        sandbox_mod._docker_is_available()


def test_sandbox_test_runner_default_enforce_follows_docker_availability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CR-004 §3.7: default-by-availability is documented in the docstring.

    The constructor's ``enforce_container_isolation=None`` default flips
    based on the Docker probe result:
      * Docker reachable → True (production posture)
      * Docker NOT reachable → False (dev posture, process runner fallback)

    The factory-method split (``SandboxTestRunner.auto()`` / ``.explicit()``)
    was considered and rejected per the "second consumer before abstraction"
    rule (only one consumer currently). The behavior is now explicitly
    documented in the constructor docstring.

    This test exercises both branches without requiring real Docker by
    monkeypatching ``_docker_is_available``.
    """
    from core.skills import sandbox as sandbox_mod

    # Branch 1: Docker reachable → enforce=True (default)
    monkeypatch.setattr(sandbox_mod, "_docker_is_available", lambda: True)
    runner_with = SandboxTestRunner()
    assert runner_with._enforce_container_isolation is True

    # Branch 2: Docker NOT reachable → enforce=False (default)
    monkeypatch.setattr(sandbox_mod, "_docker_is_available", lambda: False)
    runner_without = SandboxTestRunner()
    assert runner_without._enforce_container_isolation is False

    # Explicit override beats the default-by-availability rule.
    runner_override = SandboxTestRunner(enforce_container_isolation=True)
    assert runner_override._enforce_container_isolation is True


def test_sandbox_test_runner_explicit_runners_skip_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CR-004 §3.7: when ``runners`` is supplied, the probe is skipped.

    The auto-detection branch (``runners is None``) is purely additive;
    supplying an explicit ``runners`` list preserves the previous
    constructor contract — the probe is never called and the default
    ``enforce_container_isolation`` falls back to ``True``.
    """
    from core.skills import sandbox as sandbox_mod

    probe_called = False

    def _fake_probe() -> bool:
        nonlocal probe_called
        probe_called = True
        return True  # would otherwise force enforce=True

    monkeypatch.setattr(sandbox_mod, "_docker_is_available", _fake_probe)
    runner = SandboxTestRunner(
        runners=[ProcessSandboxRunner()],
        enforce_container_isolation=False,
    )
    assert probe_called is False
    assert runner._enforce_container_isolation is False
