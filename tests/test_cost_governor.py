"""JARVIS OS - Phase 27.B CostGovernor Tests.

Validates token pricing cost calculation, budget limit check, and non-blocking decision flow.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.observability.cost_governor import CostGovernor
from core.observability.dto import CostDecision


@pytest.fixture
def mock_budget_repo() -> MagicMock:
    repo = MagicMock()
    repo.upsert_ledger = AsyncMock()
    repo.get_daily_total = AsyncMock(return_value=0.0)
    repo.get_summary = AsyncMock()
    return repo


@pytest.fixture
def governor(mock_budget_repo: MagicMock) -> CostGovernor:
    return CostGovernor(
        budget_repository=mock_budget_repo,
        daily_limit_usd=10.0,
        warn_threshold_usd=8.0,
        per_call_block_usd=0.5,
    )


class TestCostGovernor:
    """CostGovernor verification suite (Architect constraint: non-blocking, daily + monthly logs)."""

    @pytest.mark.asyncio
    async def test_calculate_cost(self, governor: CostGovernor) -> None:
        """Verify internal cost calculation based on pricing configuration."""
        # Sonnet pricing: input=0.003, output=0.015
        cost = governor._calculate_cost("claude-3-5-sonnet", 1000, 200)
        assert cost == pytest.approx(
            0.003 + 0.003
        )  # 1000 * 0.003 / 1000 + 200 * 0.015 / 1000

    @pytest.mark.asyncio
    async def test_record_usage_allow(
        self, governor: CostGovernor, mock_budget_repo: MagicMock
    ) -> None:
        """Low token usage returns ALLOW tier and schedules async persistence."""
        decision = await governor.record_usage("claude-3-5-sonnet", 1000, 200)
        assert decision == CostDecision.ALLOW

        await asyncio.sleep(0.05)
        mock_budget_repo.upsert_ledger.assert_called_once()
        args = mock_budget_repo.upsert_ledger.call_args[0]
        # args: (date, model, tokens_in, tokens_out, cost)
        assert args[1] == "claude-3-5-sonnet"
        assert args[2] == 1000
        assert args[3] == 200
        assert args[4] == pytest.approx(0.006)

    @pytest.mark.asyncio
    async def test_record_usage_block_on_single_call(
        self, governor: CostGovernor
    ) -> None:
        """Single call exceeding $0.50 triggers CostDecision.BLOCK immediately."""
        # Opus pricing: input=0.015, output=0.075. Call with 40,000 input tokens = $0.60
        decision = await governor.record_usage("claude-3-opus", 40000, 0)
        assert decision == CostDecision.BLOCK

    @pytest.mark.asyncio
    async def test_record_usage_warn_tier(
        self, governor: CostGovernor, mock_budget_repo: MagicMock
    ) -> None:
        """If cumulative daily cost is >= warn threshold, returns WARN."""
        # Set daily total in mock to $7.99
        mock_budget_repo.get_daily_total.return_value = 7.99

        # Call costs $0.02 (1000 input * 0.015 + 100 * 0.075) = $0.015 + $0.0075 = $0.0225
        decision = await governor.record_usage("claude-3-opus", 1000, 100)
        assert decision == CostDecision.WARN

    @pytest.mark.asyncio
    async def test_record_usage_failover_tier(
        self, governor: CostGovernor, mock_budget_repo: MagicMock
    ) -> None:
        """If cumulative daily cost exceeds daily limit, returns FAILOVER."""
        mock_budget_repo.get_daily_total.return_value = 9.99
        decision = await governor.record_usage(
            "claude-3-5-sonnet", 10000, 0
        )  # cost = $0.03
        assert decision == CostDecision.FAILOVER

    @pytest.mark.asyncio
    async def test_estimate_cost(self, governor: CostGovernor) -> None:
        """estimate_cost computes estimated cost based on expected tokens."""
        est = await governor.estimate_cost("claude-3-5-sonnet", 2000)
        # Half input half output: 1000 input ($0.003) + 1000 output ($0.015) = $0.018
        assert est == pytest.approx(0.018)

    @pytest.mark.asyncio
    async def test_on_llm_response_event(
        self, governor: CostGovernor, mock_budget_repo: MagicMock
    ) -> None:
        """on_llm_response_event processes event parameters correctly without blocking."""
        event = {
            "model": "claude-3-5-sonnet",
            "input_tokens": 500,
            "output_tokens": 100,
        }
        await governor.on_llm_response_event(event)
        await asyncio.sleep(0.05)

        mock_budget_repo.upsert_ledger.assert_called_once()
        args = mock_budget_repo.upsert_ledger.call_args[0]
        assert args[1] == "claude-3-5-sonnet"
        assert args[2] == 500
        assert args[3] == 100

    @pytest.mark.asyncio
    async def test_error_resilience_on_db_failures(
        self, governor: CostGovernor, mock_budget_repo: MagicMock
    ) -> None:
        """If DB or repo raises error, governor logs and returns ALLOW (Architect C2)."""
        mock_budget_repo.get_daily_total.side_effect = RuntimeError("DB down")
        decision = await governor.record_usage("claude-3-5-sonnet", 1000, 200)
        assert decision == CostDecision.ALLOW
