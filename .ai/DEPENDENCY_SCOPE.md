# DEPENDENCY SCOPE

**Current Impact Radius (post-0.9.4):**

This file is the canonical "if I touch X, what else do I need to verify?" map. The previous version pointed at `scripts/dgv.py` and `skills/cli.py` (Phase 19/20 DGV-era work). The current state reflects the post-0.9.4 reality.

| If you change... | You must verify... | You may skip... |
|------------------|--------------------|-----------------|
| `core/skills/*` (Phase 18, 41) | `tests/test_skill_*.py`, `tests/test_runtime_fixes.py` | Memory tests, browser tests, observability tests |
| `core/runtime/persistence_db.py` (Phase 26) | `tests/test_swarm_persistence.py` | Skills tests, API gateway tests |
| `core/security/seed_service.py` (Phase 17) | `tests/test_runtime_fixes.py`, the capability-matrix smoke | Everything else |
| `api/routes/skills.py` (Phase 18) | `tests/test_skill_routes.py`, `tests/test_skill_integration.py` | Memory tests, observability tests |
| `core/observability/*` (Phase 27) | `tests/test_observability_*.py`, `tests/test_execution_tracer.py`, etc. | Skills tests, persistence tests |
| `core/memory/*` (Phase 19, 38) | `tests/test_unified_memory.py` | Skills tests, persistence tests |
| `core/workflow/*` (Phase 39) | `tests/test_workflow_graph_engine.py` | Memory tests, persistence tests |
| `core/runtime/mission.py` (Phase 34) | `tests/test_mission_*.py`, `tests/test_checkpoint.py`, `tests/test_approval_gate.py`, `tests/test_multi_agent_mission.py` | Skills tests, workflow tests |
| `core/skills/capability_registry.py` (Phase 41) | `tests/test_skill_*.py` + the capability-matrix smoke (12 probes) | Memory tests, observability tests |
| `AGENTS.md` (frozen) | n/a — AGENTS.md is the agent constitution, not a code module | All code tests |
| `JARVIS_EXECUTIVE_DASHBOARD.md` (doc) | n/a — dashboard is a tracking doc | All code tests |
| `.ai/*` (state files) | n/a — agent working memory | All code tests |
| `docs/CR/CR-XXX-*` (CR docs) | n/a — CR docs describe a future or completed change | All code tests |

**Cross-cutting rules:**

- If you change a frozen interface (see `.ai/FREEZE_LEDGER.md` and AGENTS.md §4), a Change Request (CR) is mandatory per AGENTS.md §8. No agent may self-approve a CR.
- If you change AGENTS.md itself, you must obey AGENTS.md §14: only add newly frozen phases to §12, only add new frozen interface pointers to §4, only refine the situation→context map in §3. Do not override rank-1-to-6 sources, do not introduce new architectural rules, do not authorize a frozen-interface change.
- The `wt/5432577e` and `wt/5a39ff05` branches are out of scope for verification until the architect decides what to do with them.
