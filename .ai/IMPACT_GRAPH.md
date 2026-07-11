# IMPACT GRAPH

*Rule: Use this to determine exactly which tests to rerun based on file changes. For the full per-file map, see `.ai/DEPENDENCY_SCOPE.md`.*

**If `core/skills/*` changes:**
- Need to rerun: `tests/test_skill_*.py` (skill_routes, skill_integration, skill_repository, skill_sandbox, skill_installer), `tests/test_runtime_fixes.py`
- Need NOT rerun: Memory tests, browser tests, observability tests, swarm persistence tests

**If `core/runtime/persistence_db.py` changes (Phase 26):**
- Need to rerun: `tests/test_swarm_persistence.py` (especially `TestSaveTaskRaceSafeUpsert` if you changed `_save_task_internal`)
- Need NOT rerun: Skills tests, API gateway tests, capability matrix tests

**If `core/security/seed_service.py` changes (Phase 17):**
- Need to rerun: `tests/test_runtime_fixes.py`, the capability-matrix smoke (12 probes)
- Need NOT rerun: Memory tests, observability tests, workflow tests

**If `api/routes/skills.py` changes (Phase 18):**
- Need to rerun: `tests/test_skill_routes.py`, `tests/test_skill_integration.py`
- Need NOT rerun: Memory tests, observability tests, swarm persistence tests

**If `core/observability/*` changes (Phase 27):**
- Need to rerun: `tests/test_observability_*.py`, `tests/test_execution_tracer.py`, `tests/test_cost_governor.py`, `tests/test_health_probe.py`, `tests/test_telemetry_broadcaster.py`
- Need NOT rerun: Skills tests, persistence tests, capability matrix tests

**If `core/memory/*` changes (Phase 19, 38):**
- Need to rerun: `tests/test_unified_memory.py`
- Need NOT rerun: Skills tests, persistence tests, observability tests

**If `core/workflow/*` changes (Phase 39):**
- Need to rerun: `tests/test_workflow_graph_engine.py`
- Need NOT rerun: Memory tests, persistence tests, observability tests

**If `core/runtime/mission.py` changes (Phase 34):**
- Need to rerun: `tests/test_mission_*.py`, `tests/test_checkpoint.py`, `tests/test_approval_gate.py`, `tests/test_multi_agent_mission.py`, `tests/test_mission_coverage_boost.py`
- Need NOT rerun: Skills tests, workflow tests

**If `core/skills/capability_registry.py` changes (Phase 41):**
- Need to rerun: `tests/test_skill_*.py` + the capability-matrix smoke
- Need NOT rerun: Memory tests, observability tests

**Doc-only changes (AGENTS.md, dashboard, .ai/, docs/CR/, docs/releases/):**
- Need to rerun: nothing
- Optional sanity: `git diff --name-only` to confirm no code slipped in

**Cross-cutting changes (e.g. Pydantic version bump, SQLAlchemy version bump):**
- Need to rerun: full suite
- Need to run: the capability-matrix smoke + the e2e smoke
- Need to update: the verification commands in `AGENTS.md` §9.1 if the test runner changed
