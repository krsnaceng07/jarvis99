# CONTEXT INDEX

*Rule: Do NOT scan the repo. Find what you need here.*

**Project-level:**
- Project state: `.ai/PROJECT_STATE.md`
- Current task: `.ai/CURRENT_TASK.md`
- Next action: `.ai/NEXT_ACTION.md`
- Resume state: `.ai/RESUME_STATE.md`
- Checkpoint: `.ai/CHECKPOINT.md`
- Task queue: `.ai/TASK_QUEUE.md`
- Build session: `.ai/BUILD_SESSION.md`
- Action log: `.ai/ACTION_LOG.md`
- Changeset: `.ai/CHANGESET.md`
- Dependency scope: `.ai/DEPENDENCY_SCOPE.md`
- Handoff: `.ai/HANDOFF.md`
- Quality status: `.ai/QUALITY_STATUS.md`
- Locks: `.ai/LOCKS.md`
- Impact graph: `.ai/IMPACT_GRAPH.md`
- Agent state: `.ai/AGENT_STATE.md`
- Build cache: `.ai/BUILD_CACHE.md`
- Freeze ledger: `.ai/FREEZE_LEDGER.md`

**Project governance:**
- Agent constitution: `AGENTS.md`
- Executive dashboard: `JARVIS_EXECUTIVE_DASHBOARD.md`
- Master index: `docs/60_MASTER_INDEX.md`
- Project constitution: `docs/00_PROJECT_CONSTITUTION.md`

**Code (by layer):**
- API layer: `api/` (route handlers, dependencies, broadcaster)
- Core layer: `core/` (kernel, skills, runtime, security, observability, memory, workflow, reasoning)
- Tests: `tests/`

**Tools:**
- Architecture Linter: `scripts/architecture_linter.py`
- Dependency Graph Validator (DGV): `scripts/dgv.py`
- Governance check: `scripts/governance_check.py`
- Quality gate: `scripts/quality_gate.py`
- Trace check: `scripts/trace_check.py`

**Specs (by phase):**
- Phase 1-12: `docs/74_PHASE_1_12_MASTER_SPECIFICATION.md`
- Phase 13: `docs/75_PHASE_13_MASTER_SPECIFICATION.md`
- Phase 14: `docs/76_PHASE_14_API_GATEWAY_SPECIFICATION.md`
- Phase 15: `docs/77_PHASE_15_PERSISTENT_EXECUTION_SPECIFICATION.md`
- Phase 17: `docs/78_PHASE_17_AUTHENTICATION_AUTHORIZATION_SPECIFICATION.md`
- Phase 18: `docs/79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md`
- Phase 19: `docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md`
- Phase 22: `docs/82_PHASE_22_ORCHESTRATOR_SPECIFICATION.md`
- Phase 23: `docs/83_PHASE_23_TOOL_RUNTIME_SPECIFICATION.md`
- Phase 24: `docs/84_PHASE_24_AUTONOMOUS_AGENT_SPECIFICATION.md`
- Phase 25: `docs/86_PHASE_25_BROWSER_RUNTIME_SPECIFICATION.md`
- Phase 26: `docs/87_PHASE_26_MULTI_AGENT_PERSISTENT_RECOVERY_SPECIFICATION.md`
- Phase 27: `docs/88_PHASE_27_OBSERVABILITY_COST_GOVERNANCE_SPECIFICATION.md`
- Phase 28: `docs/90_PHASE_28_SECURITY_VAULT_HARDENING_SPECIFICATION.md`
- Phase 29: `docs/91_PHASE_29_ADVANCED_VAULT_OPERATIONS_SPECIFICATION.md`
- Phase 30: `docs/92_PHASE_30_CLOUD_SYNC_HIGH_AVAILABILITY_SPECIFICATION.md`
- Phase 31: `docs/93_PHASE_31_FEDERATION_SPECIFICATION.md`
- Phase 32: `docs/94_PHASE_32_ADMINISTRATION_OPERATIONS_SPECIFICATION.md`
- Phase 33: `docs/95_PHASE_33_PRODUCTION_READINESS_SPECIFICATION.md`
- Phase 34: `docs/96_PHASE_34_AUTONOMOUS_AGENT_MISSION_SPECIFICATION.md`
- Phase 35: `docs/97_PHASE_35_DISTRIBUTED_SCALE_SPECIFICATION.md`
- Phase 36: `docs/98_PHASE_36_SWARM_INTELLIGENCE_SPECIFICATION.md`
- Phase 37: `docs/99_PHASE_37_BRAIN_KERNEL_SPECIFICATION.md`
- Phase 38: `docs/100_PHASE_38_UNIFIED_MEMORY_SPECIFICATION.md`
- Phase 39: `docs/101_PHASE_39_WORKFLOW_GRAPH_ENGINE_SPECIFICATION.md`
- Phase 40: `docs/102_PHASE_40_EVENT_BUS_REACTIVE_ARCHITECTURE_SPECIFICATION.md`
- Phase 41: `docs/103_PHASE_41_CAPABILITY_REGISTRY_SPECIFICATION.md`
- Phase 42: `docs/104_PHASE_42_IDENTITY_ENGINE_SPECIFICATION.md`
- Phase 43: `docs/105_PHASE_43_GOAL_ENGINE_SPECIFICATION.md`
- Phase 44: `docs/106_PHASE_44_MISSION_SCHEDULER_SPECIFICATION.md`
- Phase 45: (in development; spec is on branch `wt/5a39ff05` — not yet merged to main)

**CR docs (canonical record of all 0.9.x changes):**
- `docs/CR/CR-001-mission-scheduler-and-skill-read.md` (DI registration + skill.read permission)
- `docs/CR/CR-002-skill-install-remove-runtime.md` (5 skill install/remove runtime fixes)
- `docs/CR/CR-003-skills-router-mount-shadowing.md` (route-shadowing)
- `docs/CR/CR-004-cr002-static-analysis-followups.md` (7 low-severity follow-ups, all in commit `3d7383b`)
- `docs/CR/CR-005-savepoint-race-recovery-persistence.md` (SAVEPOINT-backed race recovery)

**Releases:**
- 0.9.3 v2: `docs/releases/RELEASE_0.9.3_PLATFORM_RUNTIME_STABILIZATION_v2.md` (tagged `v0.9.3-platform-runtime-stabilization-v2` at `a0e2c2a`)
- 0.9.4: SHIPPED to `origin/main` at `ce8ebdb`; no release notes doc yet (waiting on the 0.9.4 tag decision; will be `docs/releases/RELEASE_0.9.4_*.md`)
