"""
PHASE: 37
STATUS: TESTING
SPECIFICATION:
    docs/99_PHASE_37_BRAIN_KERNEL_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/PHASE_37_IMPLEMENTATION_PLAN.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from core.runtime.brain_context import BrainContext
from core.runtime.brain_events import BrainEvents
from core.runtime.brain_kernel import BrainKernel
from core.runtime.brain_state import CognitiveState
from core.runtime.neural.learning_engine import LearningEngine
from core.runtime.neural.model_router import ModelRouter
from core.runtime.neural.neural_layer import NeuralLayer
from core.runtime.neural.planning_engine import PlanningEngine
from core.runtime.neural.reasoning_engine import ReasoningEngine
from core.runtime.neural.reflection_engine import ReflectionEngine
from core.runtime.policy.decision_engine import DecisionEngine


@pytest.mark.asyncio
async def test_cognitive_state_defaults() -> None:
    """Test CognitiveState model constraints and default values."""
    state = CognitiveState()
    assert state.energy == 1.0
    assert state.confidence == 1.0
    assert state.risk_level == 0.0
    assert state.available_budget == 0.0
    assert state.estimated_cost == 0.0
    assert len(state.attention_queue) == 0


def test_brain_context_operations() -> None:
    """Test basic BrainContext storage operations."""
    context = BrainContext()
    context.set("test_key", "test_value")
    assert context.get("test_key") == "test_value"
    assert context.get("missing_key") is None

    snapshot = context.export()
    assert snapshot == {"test_key": "test_value"}

    context.clear()
    assert context.get("test_key") is None


@pytest.mark.asyncio
async def test_decision_engine_evaluation() -> None:
    """Test DecisionEngine safety policy logic."""
    engine = DecisionEngine(settings=None)
    res_safe = await engine.evaluate_action("Run safe query", {})
    assert res_safe["is_safe"] is True
    assert res_safe["requires_approval"] is False

    res_dangerous = await engine.evaluate_action("delete all tables", {})
    assert res_dangerous["requires_approval"] is True


@pytest.mark.asyncio
async def test_brain_kernel_full_cycle() -> None:
    """Test the complete Observe-Understand-Reason-Plan-Decide-Execute-Reflect-Learn loop."""
    mock_event_bus = AsyncMock()
    mock_settings = MagicMock()

    state = CognitiveState()
    context = BrainContext()

    # Setup mock router
    mock_router = AsyncMock(spec=ModelRouter)
    mock_router.route_query.return_value = "Mocked LLM Response"

    reasoning = ReasoningEngine(model_router=mock_router)
    planning = PlanningEngine(model_router=mock_router)
    reflection = ReflectionEngine(model_router=mock_router)
    learning = LearningEngine(settings=mock_settings)

    neural_layer = NeuralLayer(
        model_router=mock_router,
        reasoning_engine=reasoning,
        planning_engine=planning,
        reflection_engine=reflection,
        learning_engine=learning,
    )

    decision_engine = DecisionEngine(settings=mock_settings)

    kernel = BrainKernel(
        settings=mock_settings,
        state=state,
        context=context,
        event_bus=mock_event_bus,
        decision_engine=decision_engine,
        neural_layer=neural_layer,
    )

    # Observe
    await kernel.observe({"message": "Trigger database backup goal"})
    assert "Trigger database backup goal" in state.attention_queue
    mock_event_bus.publish.assert_any_call(
        BrainEvents.ATTENTION_SHIFT,
        {"message": "Trigger database backup goal", "queue_size": 1},
    )

    # Step Thinking Loop
    await kernel.step()

    assert state.current_goal == "Trigger database backup goal"
    assert len(state.attention_queue) == 0
    assert context.get("active_goal") == "Trigger database backup goal"
    assert state.confidence > 0.0
    assert len(learning.experiences) == 1

    from unittest.mock import ANY

    mock_event_bus.publish.assert_any_call(BrainEvents.THICK_CYCLE_START, ANY)
    mock_event_bus.publish.assert_any_call(BrainEvents.THICK_CYCLE_END, ANY)
