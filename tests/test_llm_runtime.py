"""
PHASE: 24
STATUS: TEST
SPECIFICATION:
    docs/84_PHASE_24_AUTONOMOUS_AGENT_SPECIFICATION.md

AUTHORITATIVE: NO
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.config import Settings
from core.reasoning.cost import CostGovernor
from core.reasoning.provider import IModelProvider, ProviderConfig
from core.reasoning.task import AgentTerminationReason
from core.tools.llm_runtime import LlmRequest, LlmRuntime


def _make_mock_provider(
    name: str = "mock_openai", model: str = "mock-gpt"
) -> IModelProvider:
    """Build a minimal mock IModelProvider for testing."""
    config = ProviderConfig(
        provider_name=name,
        model_name=model,
        base_url="http://localhost",
    )
    provider = MagicMock(spec=IModelProvider)
    provider.name = name
    provider.model_name = model
    provider.config = config
    provider.count_tokens = lambda text: int(len(text.split()) * 1.3)
    return provider


def _make_cost_governor() -> CostGovernor:
    settings = MagicMock(spec=Settings)
    return CostGovernor(settings=settings, db_session=None)


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_llm_runtime_basic_success() -> None:
    provider = _make_mock_provider()
    provider.generate = AsyncMock(return_value="This is the generated response.")
    gov = _make_cost_governor()

    runtime = LlmRuntime(provider=provider, cost_governor=gov)
    request = LlmRequest(prompt="Summarise the document.", category="reasoning")

    resp = await runtime.generate(request)

    assert resp.termination_reason is None
    assert resp.text == "This is the generated response."
    assert resp.provider_name == "mock_openai"
    assert resp.error is None
    assert resp.cost >= Decimal("0")


@pytest.mark.asyncio
async def test_llm_runtime_budget_exceeded() -> None:
    from core.exceptions import BudgetExceededError

    provider = _make_mock_provider()
    provider.generate = AsyncMock(return_value="should not be reached")
    gov = _make_cost_governor()
    # Override check to always raise BudgetExceededError
    gov.check_budget_limits = AsyncMock(
        side_effect=BudgetExceededError(
            code="BUDGET_DAILY_EXHAUSTED", message="Daily budget exhausted."
        )
    )

    runtime = LlmRuntime(provider=provider, cost_governor=gov)
    request = LlmRequest(prompt="Write a story.", category="reasoning")

    resp = await runtime.generate(request)

    assert resp.termination_reason == AgentTerminationReason.BUDGET_EXCEEDED
    assert resp.text == ""
    assert resp.error is not None
    provider.generate.assert_not_awaited()  # Must NOT call provider if budget exceeded


@pytest.mark.asyncio
async def test_llm_runtime_provider_error() -> None:
    provider = _make_mock_provider()
    provider.generate = AsyncMock(side_effect=ConnectionError("Provider offline"))
    gov = _make_cost_governor()

    runtime = LlmRuntime(provider=provider, cost_governor=gov)
    request = LlmRequest(prompt="Compute something.")

    resp = await runtime.generate(request)

    assert resp.termination_reason == AgentTerminationReason.FAILED
    assert "Provider offline" in (resp.error or "")


@pytest.mark.asyncio
async def test_llm_runtime_provider_name_property() -> None:
    provider = _make_mock_provider(name="anthropic")
    gov = _make_cost_governor()
    runtime = LlmRuntime(provider=provider, cost_governor=gov)
    assert runtime.provider_name == "anthropic"
