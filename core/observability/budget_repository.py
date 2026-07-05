"""
PHASE: 27
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/88_PHASE_27_OBSERVABILITY_COST_GOVERNANCE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/89_PHASE_27_IMPLEMENTATION_PLAN.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.

BudgetRepository — daily and monthly LLM cost ledger persistence.

Architect constraint C7: Tracks both daily (date) AND monthly (month) aggregates
in a single BudgetLedgerModel row per (date, month, model) combination.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.memory.database import db_manager
from core.observability.dto import BudgetSummary, CostDecision
from core.observability.models import BudgetLedgerModel

logger = logging.getLogger("jarvis.core.observability.budget_repository")

# Default budget limits (overridden by CostGovernor configuration)
_DEFAULT_DAILY_LIMIT_USD: float = 10.0
_DEFAULT_WARN_THRESHOLD_USD: float = 8.0


class BudgetRepository:
    """SQLAlchemy-backed persistence adapter for the LLM API cost ledger.

    Responsibility: upsert/query daily+monthly cost rows.
    No business logic — pure data persistence (per AGENTS.md §7.7).
    """

    def __init__(self, session_factory: Any = None) -> None:
        self._session_factory = session_factory or db_manager.session

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def upsert_ledger(
        self,
        date: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
        cost: float,
        session: Optional[AsyncSession] = None,
    ) -> None:
        """Accumulate token usage and cost into the daily+monthly ledger row.

        Architect C7: month is derived from date and stored alongside date.
        """
        month = date[:7]  # YYYY-MM-DD[:7] → YYYY-MM
        if session is not None:
            await self._upsert_internal(
                date, month, model, tokens_in, tokens_out, cost, session
            )
        else:
            async with self._session_factory() as sess:
                if not sess.in_transaction():
                    async with sess.begin():
                        await self._upsert_internal(
                            date, month, model, tokens_in, tokens_out, cost, sess
                        )
                else:
                    await self._upsert_internal(
                        date, month, model, tokens_in, tokens_out, cost, sess
                    )

    async def _upsert_internal(
        self,
        date: str,
        month: str,
        model: str,
        tokens_in: int,
        tokens_out: int,
        cost: float,
        session: AsyncSession,
    ) -> None:
        q = select(BudgetLedgerModel).where(
            BudgetLedgerModel.date == date,
            BudgetLedgerModel.model == model,
        )
        res = await session.execute(q)
        row = res.scalar_one_or_none()
        now = datetime.now(timezone.utc)

        if not row:
            row = BudgetLedgerModel(
                date=date,
                month=month,
                model=model,
                input_tokens=tokens_in,
                output_tokens=tokens_out,
                cost_usd=cost,
                call_count=1,
                updated_at=now,
            )
            session.add(row)
            logger.debug(
                "New budget ledger row: date=%s model=%s cost=%.4f", date, model, cost
            )
        else:
            row.input_tokens = (row.input_tokens or 0) + tokens_in
            row.output_tokens = (row.output_tokens or 0) + tokens_out
            row.cost_usd = (row.cost_usd or 0.0) + cost
            row.call_count = (row.call_count or 0) + 1
            row.updated_at = now
            logger.debug(
                "Updated budget ledger: date=%s model=%s cumulative=%.4f",
                date,
                model,
                row.cost_usd,
            )

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_daily_total(self, date: str) -> float:
        """Return total USD cost across all models for the given date."""
        async with self._session_factory() as sess:
            q = select(BudgetLedgerModel).where(BudgetLedgerModel.date == date)
            res = await sess.execute(q)
            rows = res.scalars().all()
            return sum(r.cost_usd or 0.0 for r in rows)

    async def get_monthly_total(self, month: str) -> float:
        """Return total USD cost across all models for the given month (YYYY-MM)."""
        async with self._session_factory() as sess:
            q = select(BudgetLedgerModel).where(BudgetLedgerModel.month == month)
            res = await sess.execute(q)
            rows = res.scalars().all()
            return sum(r.cost_usd or 0.0 for r in rows)

    async def get_summary(
        self,
        date: str,
        daily_limit_usd: float = _DEFAULT_DAILY_LIMIT_USD,
        warn_threshold_usd: float = _DEFAULT_WARN_THRESHOLD_USD,
    ) -> BudgetSummary:
        """Build a full BudgetSummary for the given date.

        Architect C7: populates both daily_ and monthly_ fields.
        """
        month = date[:7]
        async with self._session_factory() as sess:
            # Daily rows
            daily_q = select(BudgetLedgerModel).where(BudgetLedgerModel.date == date)
            daily_res = await sess.execute(daily_q)
            daily_rows = daily_res.scalars().all()

            daily_cost = sum(r.cost_usd or 0.0 for r in daily_rows)
            daily_calls = sum(r.call_count or 0 for r in daily_rows)
            daily_tokens = sum(
                (r.input_tokens or 0) + (r.output_tokens or 0) for r in daily_rows
            )

            # Monthly rows
            monthly_q = select(BudgetLedgerModel).where(
                BudgetLedgerModel.month == month
            )
            monthly_res = await sess.execute(monthly_q)
            monthly_rows = monthly_res.scalars().all()

            monthly_cost = sum(r.cost_usd or 0.0 for r in monthly_rows)
            monthly_calls = sum(r.call_count or 0 for r in monthly_rows)
            monthly_tokens = sum(
                (r.input_tokens or 0) + (r.output_tokens or 0) for r in monthly_rows
            )

        # Determine tier
        if daily_cost >= daily_limit_usd:
            tier = CostDecision.FAILOVER
        elif daily_cost >= warn_threshold_usd:
            tier = CostDecision.WARN
        else:
            tier = CostDecision.ALLOW

        return BudgetSummary(
            date=date,
            month=month,
            daily_cost_usd=daily_cost,
            monthly_cost_usd=monthly_cost,
            daily_limit_usd=daily_limit_usd,
            warn_threshold_usd=warn_threshold_usd,
            tier=tier,
            call_count_daily=daily_calls,
            total_tokens_daily=daily_tokens,
            call_count_monthly=monthly_calls,
            total_tokens_monthly=monthly_tokens,
        )
