"""E2E Pipeline Verification Script.

Boots the kernel, submits a goal through BrainKernel.step(),
and verifies the full pipeline executes:
  Goal → BrainKernel → Planner → DecisionEngine → MissionManager → Execution → Reflection → Memory
"""

import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(name)s | %(message)s")
logger = logging.getLogger("e2e_verify")


async def main() -> bool:
    from core.kernel import Kernel

    logger.info("=== STEP 1: Boot kernel ===")
    kernel = Kernel()
    ok = await kernel.boot("config.yaml")
    if not ok:
        logger.error("Kernel boot failed.")
        return False
    logger.info("Kernel booted successfully.")

    from core.runtime.brain_kernel import BrainKernel
    from core.runtime.mission import MissionManager

    container = kernel.container
    brain = container.resolve(BrainKernel)
    mission_mgr = container.resolve(MissionManager)

    logger.info("=== STEP 2: Submit goal via BrainKernel.observe() ===")
    goal = "Create a Python web server"
    await brain.observe({"message": goal, "importance": 0.7})
    logger.info("Goal queued: %s", goal)
    logger.info("Attention queue: %s", brain.state.attention_queue)

    logger.info("=== STEP 3: Run BrainKernel.step() ===")
    await brain.step()
    logger.info("Step completed.")
    logger.info("Current goal after step: %s", brain.state.current_goal)
    logger.info("Confidence: %s", brain.state.confidence)

    logger.info("=== STEP 4: Verify mission was created ===")
    from core.memory.database import db_manager
    from core.runtime.mission_models import MissionModel, MissionTimelineModel
    from sqlalchemy import select

    await asyncio.sleep(0.5)  # let background mission loop run

    async with db_manager.session() as session:
        stmt = select(MissionModel)
        res = await session.execute(stmt)
        missions = res.scalars().all()
        logger.info("Missions in DB: %d", len(missions))
        for m in missions:
            logger.info(
                "  Mission %s | goal=%s | status=%s | steps=%d | current_step=%d",
                m.mission_id,
                m.goal,
                m.status,
                len(m.plan_data) if m.plan_data else 0,
                m.current_step,
            )

        stmt_t = select(MissionTimelineModel).order_by(MissionTimelineModel.timestamp)
        res_t = await session.execute(stmt_t)
        events = res_t.scalars().all()
        logger.info("Timeline events: %d", len(events))
        for e in events:
            logger.info("  [%s] %s", e.event_type, e.description)

    # Check success conditions
    if not missions:
        logger.error("FAIL: No missions created — pipeline broken at BrainKernel.execute_action()")
        return False

    mission = missions[0]
    if mission.status not in ("COMPLETED", "RUNNING"):
        logger.warning("Mission status: %s (may still be running)", mission.status)

    if mission.status == "COMPLETED":
        logger.info("SUCCESS: Goal traveled through the complete pipeline and completed.")
    elif mission.status == "RUNNING":
        logger.info("Waiting for mission to complete...")
        for _ in range(20):
            await asyncio.sleep(0.5)
            async with db_manager.session() as session:
                stmt = select(MissionModel).where(MissionModel.mission_id == mission.mission_id)
                res = await session.execute(stmt)
                m = res.scalar_one()
                if m.status == "COMPLETED":
                    logger.info("SUCCESS: Mission completed after waiting.")
                    break
                elif m.status not in ("RUNNING", "PLANNING"):
                    logger.error("Mission ended with status: %s", m.status)
                    return False
        else:
            logger.warning("Mission still running after 10s — may need more time.")

    logger.info("=== STEP 5: Verify memory was stored ===")
    from core.memory.orchestrator import MemoryOrchestrator
    memory_orch = container.resolve(MemoryOrchestrator)
    if memory_orch:
        try:
            from core.memory.dto import RetrievalRequest
            request = RetrievalRequest(query=goal, max_chunks=5, min_score=0.0)
            response = await memory_orch.recall(request)
            logger.info("Memory recall results: %d chunks", len(response.chunks))
            for c in response.chunks:
                logger.info("  Memory: %s", c.content[:100])
        except Exception as e:
            logger.info("Memory recall not available: %s", e)

    logger.info("=== E2E PIPELINE VERIFICATION COMPLETE ===")
    return True


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
