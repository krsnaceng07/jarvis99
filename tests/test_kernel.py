"""JARVIS OS - System Kernel Unit Tests.

Verifies bootstrap flows and active kernel setups.
"""

from unittest.mock import AsyncMock

import pytest

from core.exceptions import JarvisSystemError
from core.interfaces import LifecycleInterface
from core.kernel import Kernel
from core.lifecycle import LifecycleState


@pytest.mark.asyncio
async def test_kernel_boot_sequence() -> None:
    """Verify Kernel boots correctly and registers itself."""
    kernel = Kernel()
    await kernel.initialize()

    # Verify kernel registered in container
    resolved_kernel = kernel.container.resolve(LifecycleInterface)  # type: ignore[type-abstract]
    assert resolved_kernel is kernel

    # Mock internal methods using setattr to bypass Mypy method-assign rule
    setattr(kernel, "_load_vault", AsyncMock(return_value=True))
    setattr(kernel, "_initialize_event_bus", AsyncMock(return_value=True))

    boot_success = await kernel.boot(config_path="config.yaml")
    assert boot_success
    assert kernel.lifecycle_manager.state is LifecycleState.RUNNING

    await kernel.lifecycle_manager.stop_all()
    await kernel.lifecycle_manager.shutdown_all()
    assert kernel.lifecycle_manager.state is LifecycleState.SHUTDOWN  # type: ignore[comparison-overlap]


@pytest.mark.asyncio
async def test_kernel_boot_failures() -> None:
    """Verify Kernel handles various boot-time failures correctly."""
    # 1. Already booted failure
    kernel = Kernel()
    await kernel.initialize()
    setattr(kernel, "_load_vault", AsyncMock(return_value=True))
    setattr(kernel, "_initialize_event_bus", AsyncMock(return_value=True))
    boot_success = await kernel.boot(config_path="config.yaml")
    assert boot_success

    with pytest.raises(JarvisSystemError) as exc_info:
        await kernel.boot(config_path="config.yaml")
    assert exc_info.value.code == "SYSTEM_001"
    assert "already booted" in exc_info.value.message

    await kernel.lifecycle_manager.stop_all()
    await kernel.lifecycle_manager.shutdown_all()

    # 2. Vault load failure
    kernel2 = Kernel()
    await kernel2.initialize()
    setattr(kernel2, "_load_vault", AsyncMock(return_value=False))
    setattr(kernel2, "_initialize_event_bus", AsyncMock(return_value=True))
    boot_success2 = await kernel2.boot(config_path="config.yaml")
    assert not boot_success2

    # 3. Event bus init failure
    kernel3 = Kernel()
    await kernel3.initialize()
    setattr(kernel3, "_load_vault", AsyncMock(return_value=True))
    setattr(kernel3, "_initialize_event_bus", AsyncMock(return_value=False))
    boot_success3 = await kernel3.boot(config_path="config.yaml")
    assert not boot_success3


@pytest.mark.asyncio
async def test_kernel_default_hooks() -> None:
    """Verify Kernel baseline hook methods (e.g. _load_vault, _initialize_event_bus) return expected outcomes."""
    kernel = Kernel()
    await kernel.initialize()

    # Calling default hooks (no mock)
    vault_ok = await kernel._load_vault()
    assert vault_ok

    eb_ok = await kernel._initialize_event_bus()
    assert eb_ok

    # Shutdown sequence
    await kernel.start()
    await kernel.stop()
    await kernel.shutdown()
