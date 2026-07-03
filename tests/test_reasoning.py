"""JARVIS OS - Reasoning Engine & Agent Planner Unit Tests.

Validates model providers, health circuit breakers, cost budget restrictions, structured planning DTOs,
execution orchestrators, and early-stopping reflection loops.
"""

import json
from decimal import Decimal
from typing import Any, AsyncIterator, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import select

from core.config import Settings
from core.exceptions import BudgetExceededError, JarvisSkillError, JarvisSystemError
from core.memory.database import db_manager
from core.memory.models import Base
from core.reasoning.cost import CostGovernor
from core.reasoning.orchestrator import ExecutionOrchestrator
from core.reasoning.planner import (
    PlanHistory,
    PlanResult,
    ReasoningSession,
    ReasoningSessionRecord,
    ReasoningTrace,
)
from core.reasoning.prompt import PromptBuilder
from core.reasoning.provider import (
    ClaudeProvider,
    GeminiProvider,
    LlamaProvider,
    ModelHealthStatus,
    OpenAIProvider,
    QwenProvider,
)
from core.reasoning.reflection import ReflectionEngine
from core.reasoning.router import ModelRouter
from core.tools.base import ToolExecutionResult
from core.tools.runtime import ToolRuntime


async def mock_urllib_request(
    self: Any,
    method: str,
    url: str,
    headers: Dict[str, str],
    data: Optional[bytes] = None,
    timeout: float = 30.0,
) -> bytes:
    prompt = "test"
    model = ""
    if data:
        try:
            payload = json.loads(data.decode("utf-8"))
            if "contents" in payload:
                prompt = payload["contents"][0]["parts"][0]["text"]
            elif "messages" in payload:
                prompt = payload["messages"][-1]["content"]
            elif "prompt" in payload:
                prompt = payload["prompt"]
            if "model" in payload:
                model = payload["model"].lower()
        except Exception:
            pass

    if "generativelanguage" in url:
        return json.dumps(
            {"candidates": [{"content": {"parts": [{"text": f"[Gemini: {prompt}]"}]}}]}
        ).encode("utf-8")
    elif "anthropic" in url:
        return json.dumps(
            {"content": [{"type": "text", "text": f"[Claude: {prompt}]"}]}
        ).encode("utf-8")
    elif "openai" in url:
        return json.dumps(
            {
                "choices": [
                    {"message": {"role": "assistant", "content": f"[OpenAI: {prompt}]"}}
                ]
            }
        ).encode("utf-8")
    elif "qwen" in model or "qwen" in url:
        return json.dumps(
            {"message": {"role": "assistant", "content": f"[Qwen: {prompt}]"}}
        ).encode("utf-8")
    else:
        return json.dumps(
            {"message": {"role": "assistant", "content": f"[Llama: {prompt}]"}}
        ).encode("utf-8")


async def mock_urllib_stream_request(
    self: Any,
    method: str,
    url: str,
    headers: Dict[str, str],
    data: Optional[bytes] = None,
    timeout: float = 30.0,
) -> AsyncIterator[bytes]:
    prompt = "test"
    model = ""
    if data:
        try:
            payload = json.loads(data.decode("utf-8"))
            if "contents" in payload:
                prompt = payload["contents"][0]["parts"][0]["text"]
            elif "messages" in payload:
                prompt = payload["messages"][-1]["content"]
            elif "prompt" in payload:
                prompt = payload["prompt"]
            if "model" in payload:
                model = payload["model"].lower()
        except Exception:
            pass

    if "anthropic" in url:
        chunks = [
            f'data: {{"type": "content_block_delta", "delta": {{"type": "text_delta", "text": "[Claude: {prompt}]"}}}}\n'.encode(
                "utf-8"
            ),
            b"data: [DONE]\n",
        ]
    elif "openai" in url:
        chunks = [
            f'data: {{"choices": [{{"delta": {{"content": "[OpenAI: {prompt}]"}}}}]}}\n'.encode(
                "utf-8"
            ),
            b"data: [DONE]\n",
        ]
    elif "generativelanguage" in url:
        chunks = [
            f'{{"candidates": [{{"content": {{"parts": [{{"text": "[Gemini: {prompt}]"}}]}}}}]}}'.encode(
                "utf-8"
            ),
        ]
    else:
        # qwen or llama
        name = "Qwen" if ("qwen" in model or "qwen" in url) else "Llama"
        chunks = [
            f'{{"message": {{"content": "[{name}: {prompt}]"}}, "done": true}}'.encode(
                "utf-8"
            ),
        ]

    async def generator() -> AsyncIterator[bytes]:
        for chunk in chunks:
            yield chunk

    return generator()


@pytest.fixture(autouse=True)
def mock_transport_network(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "core.reasoning.transport.UrllibTransport.request", mock_urllib_request
    )
    monkeypatch.setattr(
        "core.reasoning.transport.UrllibTransport.stream_request",
        mock_urllib_stream_request,
    )


@pytest.fixture
async def db_session() -> Any:
    """Provides a transactional database session over an in-memory SQLite setup."""
    settings = Settings.load_settings()
    db_manager.init(settings, connection_url="sqlite+aiosqlite:///:memory:")

    # Create all tables (including ReasoningSessionRecord and PlanHistory tables)
    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(Base.metadata.create_all)

    async with db_manager.session() as session:
        yield session

    await db_manager.close()


def create_test_router(
    providers: List[Any], settings: Settings, cost_gov: CostGovernor
) -> ModelRouter:
    from core.reasoning.rate_limiter import ProviderRateLimiter
    from core.reasoning.registry import ModelCapabilityRegistry
    from core.reasoning.telemetry import ReasoningTelemetry

    registry = ModelCapabilityRegistry()
    for p in providers:
        registry.register_provider_config(p.config)
    rate_limiter = ProviderRateLimiter()
    telemetry = ReasoningTelemetry()

    return ModelRouter(
        providers=providers,
        registry=registry,
        rate_limiter=rate_limiter,
        telemetry=telemetry,
        cost_gov=cost_gov,
        settings=settings,
    )


@pytest.mark.asyncio
async def test_model_providers_and_health_states() -> None:
    """Verify provider generation stubs and circuit breaker transition states."""
    provider = GeminiProvider()
    assert provider.name == "gemini"
    assert provider.supports_vision() is True
    assert provider.supports_tools() is True

    # Check health checks
    status = await provider.health_check()
    assert status == ModelHealthStatus.ONLINE

    # Verify failure record pushes state to COOLDOWN
    provider.record_failure()
    status = await provider.health_check()
    assert status == ModelHealthStatus.COOLDOWN

    # Verify multiple failures push state to OFFLINE
    for _ in range(5):
        provider.record_failure()
    status = await provider.health_check()
    assert status == ModelHealthStatus.OFFLINE

    # Success records reset health
    provider.record_success()
    status = await provider.health_check()
    assert status == ModelHealthStatus.ONLINE


@pytest.mark.asyncio
async def test_model_router_priority_mappings() -> None:
    """Verify ModelRouter correctly resolves priority task categories and fallbacks."""
    settings = Settings.load_settings()
    gemini = GeminiProvider()
    claude = ClaudeProvider()
    qwen = QwenProvider()
    llama = LlamaProvider()

    cost_gov = CostGovernor(settings)
    router = create_test_router([gemini, claude, qwen, llama], settings, cost_gov)

    # 1. Normal resolution: Coding -> Claude
    provider = await router.get_provider_for_task("Coding")
    assert provider.name == "claude"

    # 2. Cooldown fallback: Trigger Claude failure -> Should fallback to openai (if configured) or qwen/next candidate
    # Let's set claude to offline
    for _ in range(5):
        claude.record_failure()

    # Coding candidates: ["claude", "openai", "qwen"] -> Should resolve to qwen since OpenAI is not initialized
    provider = await router.get_provider_for_task("Coding")
    assert provider.name == "qwen"

    # 3. Exhaustion failover: If all candidates fail, fall back to any online provider
    for _ in range(5):
        qwen.record_failure()

    # Only gemini and llama are left online. Coding should fall back to gemini
    provider = await router.get_provider_for_task("Coding")
    assert provider.name == "gemini"


@pytest.mark.asyncio
async def test_cost_governor_budget_restrictions() -> None:
    """Verify CostGovernor calculates pricing weights and gates budget violations."""
    settings = Settings.load_settings()
    cost_gov = CostGovernor(settings)

    # 1. Cost estimation
    prompt = "Hello world this is a test prompt statement."
    cost = cost_gov.estimate_cost(prompt, "claude")
    # 8 words * 1.3 = 10 tokens. Rate for Claude = 0.0015 per 1k input tokens.
    assert cost > 0

    # 2. Budget limits checking
    await cost_gov.check_budget_limits(Decimal("0.01"))  # safe cost

    # Per-call budget gate trigger ($0.50 USD threshold limit)
    with pytest.raises(JarvisSystemError) as exc_system:
        await cost_gov.check_budget_limits(Decimal("0.60"))
    assert exc_system.value.code == "BUDGET_PER_CALL_EXCEEDED"

    # Daily budget exhaustion limit
    cost_gov.cached_daily_spending = Decimal("9.99")
    with pytest.raises(BudgetExceededError) as exc_budget:
        await cost_gov.check_budget_limits(Decimal("0.05"))
    assert exc_budget.value.code == "BUDGET_DAILY_EXHAUSTED"

    # Monthly budget exhaustion limit
    cost_gov.reset_spending()
    cost_gov.cached_monthly_spending = Decimal("99.99")
    with pytest.raises(BudgetExceededError) as exc_monthly:
        await cost_gov.check_budget_limits(Decimal("0.05"))
    assert exc_monthly.value.code == "BUDGET_MONTHLY_EXHAUSTED"


def test_prompt_builder_budget_compressions() -> None:
    """Verify PromptBuilder concatenations and token budget compression."""
    builder = PromptBuilder(max_context_tokens=100)

    # Simple prompt assembling
    prompt = builder.build_prompt(
        system_prompt="Standard system directive.",
        user_goal="Accomplish task A",
        memories=["Memory 1", "Memory 2"],
    )
    assert "Standard system directive" in prompt
    assert "Memory 1" in prompt
    assert "Accomplish task A" in prompt

    # Force token context compression with a very long history payload
    long_history = [{"role": "user", "content": "hello " * 300}]
    compressed_prompt = builder.build_prompt(
        system_prompt="Short prompt.",
        user_goal="Goal",
        history=long_history,
    )
    assert "[truncated context due to budget]" in compressed_prompt


@pytest.mark.asyncio
async def test_planner_goal_decomposition_waves_and_history() -> None:
    """Verify GoalStackPlanner decomposes requests to structured waves and records histories."""
    settings = Settings.load_settings()
    gemini = GeminiProvider()
    cost_gov = CostGovernor(settings)
    router = create_test_router([gemini], settings, cost_gov)
    prompt_builder = PromptBuilder()

    session_id = uuid4()
    goal_id = uuid4()
    session = ReasoningSession(session_id, goal_id, db_session=None)

    # 1. Successful goal decomposition (max 3 independent tasks per wave rule)
    goal = "Create database structure, Write profile REST endpoints, Compile styling layout sheets"
    plan: PlanResult = await session.decompose_goal(
        goal=goal,
        prompt_builder=prompt_builder,
        router=router,
        cost_gov=cost_gov,
    )

    assert plan.goal == goal
    assert len(plan.waves) == 1
    assert len(plan.waves[0]) == 3  # exactly 3 independent tasks
    assert plan.requires_approval is False

    # 2. Strict wave size rule validation: should raise error if waves have > 3 tasks
    # We will simulate a manual wave insert that violates this limit
    session.plan_version = 2
    # Mock planning generating more than 3 tasks in a single wave
    invalid_goal = "t1, t2, t3, t4"
    # To check that planner handles grouping, a goal with 4 tasks splits into 2 waves: Wave 0 (3 tasks), Wave 1 (1 task)
    plan2 = await session.decompose_goal(
        goal=invalid_goal,
        prompt_builder=prompt_builder,
        router=router,
        cost_gov=cost_gov,
    )
    assert len(plan2.waves) == 2
    assert len(plan2.waves[0]) == 3
    assert len(plan2.waves[1]) == 1

    # 3. Telemetry tracing verify
    trace: ReasoningTrace = session.generate_trace("SUCCESS")
    assert trace.session_id == session_id
    assert trace.selected_model == "gemini"
    assert trace.latency_ms > 0.0


@pytest.mark.asyncio
async def test_execution_orchestrator_tool_mediator() -> None:
    """Verify ExecutionOrchestrator directs tool runtime runs, retrying on exceptions."""
    settings = Settings.load_settings()
    mock_tool_runtime = MagicMock(spec=ToolRuntime)

    orchestrator = ExecutionOrchestrator(mock_tool_runtime, settings)
    session_id = uuid4()
    goal_id = uuid4()
    session = ReasoningSession(session_id, goal_id)

    # 1. Successful execution
    mock_result = ToolExecutionResult(
        exit_code=0,
        stdout="success output",
        stderr="",
        duration=0.5,
        audit_id=uuid4(),
    )
    mock_tool_runtime.execute_tool = AsyncMock(return_value=mock_result)

    res = await orchestrator.execute_task_step(
        tool_name="file-writer",
        arguments={"command": ["write"]},
        session=session,
    )
    assert res["status"] == "SUCCESS"
    assert res["stdout"] == "success output"
    assert len(session.tool_calls) == 1
    assert session.tool_calls[0]["status"] == "success"

    # 2. Failure retry simulation: raise JarvisSkillError, retry up to 2 times
    mock_tool_runtime.execute_tool = AsyncMock(
        side_effect=JarvisSkillError(code="SKILL_999", message="Fail")
    )
    res_fail = await orchestrator.execute_task_step(
        tool_name="unstable-tool",
        arguments={},
        session=session,
    )
    assert res_fail["status"] == "ERROR"
    assert "Fail" in res_fail["error"]
    assert mock_tool_runtime.execute_tool.call_count == 3  # initial + 2 retries


@pytest.mark.asyncio
async def test_reflection_engine_early_stops() -> None:
    """Verify ReflectionEngine count limits and early confidence stops."""
    settings = Settings.load_settings()
    engine = ReflectionEngine(settings)

    session_id = uuid4()
    goal_id = uuid4()
    session = ReasoningSession(session_id, goal_id, budget=5.0)

    # 1. Success execution path
    res = await engine.reflect_and_correct(
        task_name="Verify database connection",
        execution_result={"status": "SUCCESS"},
        session=session,
    )
    assert res["status"] == "RESOLVED"
    assert res["reason"] == "SUCCESS"
    assert res["reflection_count"] == 1

    # Reset session counts
    session.reflection_count = 0

    # 2. Failure reflection iteration loops
    # First attempt: low confidence (0.75) -> returns RETRY
    res_retry1 = await engine.reflect_and_correct(
        task_name="Compile code",
        execution_result={"status": "FAILURE"},
        session=session,
    )
    assert res_retry1["status"] == "RETRY"
    assert res_retry1["reflection_count"] == 1

    # Second attempt: confidence increases to 0.60 + (2 * 0.15) = 0.90 -> matches target confidence (0.90) -> early stops!
    res_retry2 = await engine.reflect_and_correct(
        task_name="Compile code",
        execution_result={"status": "FAILURE"},
        session=session,
        target_confidence=0.90,
    )
    assert res_retry2["status"] == "RESOLVED"
    assert res_retry2["reason"] == "SUCCESS"
    assert res_retry2["reflection_count"] == 2

    # Reset count
    session.reflection_count = 0

    # 3. Maximum attempts limit ceiling (3 attempts)
    await engine.reflect_and_correct(
        "Compile", {"status": "FAILURE"}, session, target_confidence=0.99
    )
    await engine.reflect_and_correct(
        "Compile", {"status": "FAILURE"}, session, target_confidence=0.99
    )
    res_max = await engine.reflect_and_correct(
        "Compile", {"status": "FAILURE"}, session, target_confidence=0.99
    )
    assert res_max["status"] == "FAILED"
    assert res_max["reason"] == "MODEL_FAILURE"
    assert res_max["reflection_count"] == 3


@pytest.mark.asyncio
async def test_reasoning_database_persistence(db_session: Any) -> None:
    """Verify database persistence of ReasoningSessionRecord and PlanHistory."""
    settings = Settings.load_settings()
    gemini = GeminiProvider()
    cost_gov = CostGovernor(settings)
    router = create_test_router([gemini], settings, cost_gov)
    prompt_builder = PromptBuilder()

    session_id = uuid4()
    goal_id = uuid4()
    session = ReasoningSession(session_id, goal_id, db_session=db_session)

    # Trigger goal decomposition which calls database inserts
    goal = "Verify connection, Insert seed records"
    await session.decompose_goal(
        goal=goal,
        prompt_builder=prompt_builder,
        router=router,
        cost_gov=cost_gov,
    )

    # 1. Query ReasoningSessionRecord
    stmt = select(ReasoningSessionRecord).where(
        ReasoningSessionRecord.id == str(session_id)
    )
    res = await db_session.execute(stmt)
    record = res.scalar_one_or_none()
    assert record is not None
    assert record.goal_id == str(goal_id)

    # 2. Query PlanHistory
    stmt_history = select(PlanHistory).where(PlanHistory.goal_id == str(goal_id))
    res_history = await db_session.execute(stmt_history)
    histories = res_history.scalars().all()
    assert len(histories) == 1
    assert histories[0].version == 1


@pytest.mark.asyncio
async def test_reasoning_edge_cases_coverage() -> None:
    """Exercise remaining branches in router, cost, prompt, providers, and reflection to hit 100% coverage."""
    settings = Settings.load_settings()

    cost_gov = CostGovernor(settings)
    empty_router = create_test_router([], settings, cost_gov)
    with pytest.raises(JarvisSystemError) as exc_empty:
        await empty_router.get_provider_for_task("NonExistent")
    assert exc_empty.value.code == "ROUTER_002"

    # Default fallback when category is missing from matrix
    gemini = GeminiProvider()
    one_provider_router = create_test_router([gemini], settings, cost_gov)
    prov = await one_provider_router.get_provider_for_task("NonExistent")
    assert prov.name == "gemini"

    # 2. Providers: generate/stream coverages
    claude = ClaudeProvider()
    assert "[Claude:" in await claude.generate("test")
    async for chunk in await claude.stream_generate("test"):
        assert "Claude" in chunk

    openai = OpenAIProvider()
    assert "[OpenAI:" in await openai.generate("test")
    async for chunk in await openai.stream_generate("test"):
        assert "OpenAI" in chunk

    qwen = QwenProvider()
    assert "[Qwen:" in await qwen.generate("test")
    async for chunk in await qwen.stream_generate("test"):
        assert "Qwen" in chunk
    assert qwen.supports_vision() is False

    llama = LlamaProvider()
    assert "[Llama:" in await llama.generate("test")
    async for chunk in await llama.stream_generate("test"):
        assert "Llama" in chunk
    assert llama.supports_tools() is False

    # 3. PromptBuilder context inputs
    builder = PromptBuilder()
    prompt = builder.build_prompt(
        system_prompt="sys",
        user_goal="goal",
        project_context="active project",
        tool_results=[
            {"tool_name": "my-tool", "status": "success", "output": "output text"}
        ],
    )
    assert "active project" in prompt
    assert "Tool [my-tool]" in prompt

    # 4. Cost/Reflection budget exceedance early stop
    engine = ReflectionEngine(settings)
    session_id = uuid4()
    goal_id = uuid4()
    session = ReasoningSession(session_id, goal_id, budget=1.0)
    session.total_cost = 2.0  # budget exceeded

    res_stop = await engine.reflect_and_correct(
        task_name="Verify database",
        execution_result={"status": "FAILURE"},
        session=session,
    )
    assert res_stop["status"] == "STOPPED"
    assert res_stop["reason"] == "BUDGET_EXCEEDED"

    # 5. Planner goal splitting fallback
    cost_gov = CostGovernor(settings)
    router = create_test_router([gemini], settings, cost_gov)
    session_planner = ReasoningSession(session_id, goal_id)
    # goal without separator
    plan = await session_planner.decompose_goal("", builder, router, cost_gov)
    assert len(plan.waves) == 1
