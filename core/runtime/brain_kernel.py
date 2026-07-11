"""
PHASE: 37
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/99_PHASE_37_BRAIN_KERNEL_SPECIFICATION.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

import logging
from typing import Any, Dict, Optional

from core.runtime.brain_context import BrainContext
from core.runtime.brain_events import BrainEvents
from core.runtime.brain_state import CognitiveState
from core.runtime.neural.neural_layer import NeuralLayer
from core.runtime.policy.decision_engine import DecisionEngine

logger = logging.getLogger(__name__)


class BrainKernel:
    """The central orchestrator of cognitive states and thinking loops."""

    def __init__(
        self,
        settings: Any,
        state: CognitiveState,
        context: BrainContext,
        event_bus: Optional[Any] = None,
        decision_engine: Optional[DecisionEngine] = None,
        neural_layer: Optional[NeuralLayer] = None,
        mission_manager: Optional[Any] = None,
        identity_service: Optional[Any] = None,
        memory_orchestrator: Optional[Any] = None,
    ) -> None:
        """Initialize the Brain Kernel."""
        self.settings = settings
        self.state = state
        self.context = context
        self.event_bus = event_bus
        self.decision_engine = decision_engine
        self.neural_layer = neural_layer
        self.mission_manager = mission_manager
        self.identity_service = identity_service
        self.memory_orchestrator = memory_orchestrator
        self._is_running = False

    async def get_active_identity(self) -> Optional[Any]:
        """Retrieve the active identity from the identity service if configured."""
        if self.identity_service:
            return await self.identity_service.get_active_identity()
        return None

    async def observe(self, observation: Dict[str, Any]) -> None:
        """Process inbound observations and append to attention queue."""
        logger.info("Processing observation in BrainKernel: %s", observation)
        msg = observation.get("message")
        if msg:
            self.state.attention_queue.append(msg)
            if self.event_bus:
                await self.event_bus.publish(
                    BrainEvents.ATTENTION_SHIFT,
                    {"message": msg, "queue_size": len(self.state.attention_queue)},
                )
            # Phase 19 — store observation as working-tier memory
            if self.memory_orchestrator:
                try:
                    await self.memory_orchestrator.store(
                        content=msg,
                        source_type="observation",
                        metadata={"origin": "brain_kernel.observe"},
                        importance=observation.get("importance", 0.3),
                    )
                except Exception as e:
                    logger.debug("Memory store during observe skipped: %s", e)

    async def understand(self, goal: str) -> Dict[str, Any]:
        """Understand the current goal context and set active attention details."""
        logger.info("BrainKernel understanding active goal: %s", goal)
        self.context.set("active_goal", goal)
        return {"goal": goal, "context_keys": list(self.context.export().keys())}

    async def reason(self) -> Dict[str, Any]:
        """Run thinking loops over the active goal stack and state context."""
        logger.info("Reasoning loop execution requested.")
        if not self.state.current_goal and self.state.attention_queue:
            self.state.current_goal = self.state.attention_queue.pop(0)

        goal = self.state.current_goal or "idle"

        # Phase 19 — recall relevant memories to enrich reasoning context
        memory_context: list[Any] = []
        if self.memory_orchestrator and goal != "idle":
            try:
                from core.memory.dto import RetrievalRequest

                request = RetrievalRequest(query=goal, max_chunks=5, min_score=0.0)
                response = await self.memory_orchestrator.recall(request)
                memory_context = [
                    {"content": c.content, "memory_id": str(c.memory_id)}
                    for c in response.chunks
                ]
                self.context.set("memory_context", memory_context)
            except Exception as e:
                logger.debug("Memory recall during reason skipped: %s", e)

        if self.neural_layer:
            analysis = await self.neural_layer.reasoning_engine.analyze(
                goal, self.context.export()
            )
            self.state.confidence = analysis.get("confidence", 1.0)
        else:
            self.state.confidence = 1.0

        return {
            "current_goal": self.state.current_goal,
            "confidence": self.state.confidence,
            "energy": self.state.energy,
        }

    async def plan(self) -> Dict[str, Any]:
        """Decompose active goal into discrete tasks using the planning engine."""
        goal = self.state.current_goal or "idle"
        logger.info("Planning tasks for goal: %s", goal)

        if self.neural_layer:
            steps = await self.neural_layer.planning_engine.generate_plan(
                goal, self.context.export()
            )
            return {"steps": steps}

        return {"steps": [{"step_index": 1, "task": f"Decompose: {goal}"}]}

    async def decide(self, goal: str) -> Dict[str, Any]:
        """Verify action safety and routing policies with the DecisionEngine."""
        if self.decision_engine:
            decision = await self.decision_engine.evaluate_action(
                goal, self.context.export()
            )
            self.state.estimated_cost = decision.get("estimated_cost_usd", 0.0)
            return decision

        return {"is_safe": True, "requires_approval": False}

    async def execute_action(
        self,
        goal: str,
        decision: Dict[str, Any],
        plan_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Delegate tasks and execute actions via MissionManager interfaces."""
        logger.info("Executing action for goal: %s", goal)
        if not decision.get("is_safe", True):
            logger.warning("Execution blocked by DecisionEngine policy.")
            return {"status": "BLOCKED", "reason": "Safety check failed"}

        if self.mission_manager:
            try:
                logger.info("Delegating goal to mission manager.")
                plan_steps = (plan_result or {}).get("steps")
                mission_result = await self.mission_manager.create_mission(
                    goal, plan_steps=plan_steps,
                )
                mission_id = mission_result["mission_id"]
                start_result = await self.mission_manager.start_mission(mission_id)
                return {
                    "status": "SUCCESS",
                    "goal": goal,
                    "mission_id": str(mission_id),
                    "steps": start_result.get("steps", []),
                }
            except Exception as e:
                logger.error("MissionManager delegation failed: %s", str(e))
                return {"status": "FAILED", "goal": goal, "error": str(e)}

        return {"status": "SUCCESS", "goal": goal}

    async def reflect_and_learn(
        self, goal: str, execution_result: Dict[str, Any]
    ) -> None:
        """Analyze execution results and update cognitive confidence levels."""
        logger.info("BrainKernel starting reflection and learning cycle.")
        reflection: Optional[Dict[str, Any]] = None
        if self.neural_layer:
            metadata = {
                "goal": goal,
                "status": execution_result.get("status", "SUCCESS"),
                "confidence": self.state.confidence,
                "cost": self.state.estimated_cost,
            }
            reflection = await self.neural_layer.reflection_engine.reflect(metadata)
            self.state.confidence += reflection.get("confidence_adjustment", 0.0)
            self.state.confidence = max(0.0, min(1.0, self.state.confidence))

            await self.neural_layer.learning_engine.ingest_experience(metadata)

        if self.memory_orchestrator:
            status = execution_result.get("status", "SUCCESS")
            try:
                await self.memory_orchestrator.store(
                    content=f"Executed goal '{goal}': {status}",
                    source_type="execution_experience",
                    metadata={
                        "origin": "brain_kernel.reflect_and_learn",
                        "goal": goal,
                        "status": status,
                        "confidence": self.state.confidence,
                    },
                    importance=0.6 if status == "SUCCESS" else 0.8,
                )
            except Exception as e:
                logger.debug("Memory store during reflect skipped: %s", e)

            if reflection:
                critique = reflection.get("reflection_critique", "")
                is_correct = reflection.get("is_correct", True)
                try:
                    await self.memory_orchestrator.store(
                        content=(
                            f"Reflection on '{goal}': "
                            f"{'succeeded' if is_correct else 'failed'}. "
                            f"{critique}"
                        ),
                        source_type="reflection_insight",
                        metadata={
                            "origin": "brain_kernel.reflect_and_learn",
                            "goal": goal,
                            "is_correct": is_correct,
                            "confidence_after": self.state.confidence,
                            "memory_type": "event",
                            "tier": "long_term",
                        },
                        importance=0.7 if is_correct else 0.9,
                        confidence=self.state.confidence,
                    )
                except Exception as e:
                    logger.debug("Reflection memory store skipped: %s", e)

    async def step(self) -> None:
        """Execute one cycle of the Observe-Understand-Reason-Plan-Decide-Execute-Reflect-Learn loop."""
        if self.event_bus:
            await self.event_bus.publish(
                BrainEvents.THICK_CYCLE_START, {"state": self.state.model_dump()}
            )

        # 1. Observe (Queue check)
        if not self.state.current_goal and self.state.attention_queue:
            self.state.current_goal = self.state.attention_queue.pop(0)

        goal = self.state.current_goal or "idle"

        # 2. Understand
        await self.understand(goal)

        # 3. Reason
        await self.reason()

        # 4. Plan
        plan_result = await self.plan()

        # 5. Decide
        decision = await self.decide(goal)

        # 6. Execute
        exec_res = await self.execute_action(goal, decision, plan_result)

        # 7. Reflect & Learn
        await self.reflect_and_learn(goal, exec_res)

        if self.event_bus:
            await self.event_bus.publish(
                BrainEvents.THICK_CYCLE_END, {"state": self.state.model_dump()}
            )
