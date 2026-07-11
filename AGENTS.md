# AGENTS.md — JARVIS OS Canonical Agent Entry-Point

## Status: AUTHORITATIVE NAVIGATION DOCUMENT (not a rule source)
## Version: 1.0 — Established post-Phase 13 freeze (2026-06-28)

---

## 0. What This Document IS and IS NOT

**This document IS:**
- The single canonical entry-point for ANY agent (Cursor, Claude Code, GLM, Zed) working in this repo.
- An **authority ranking** — when documents conflict, this file declares who wins.
- A **navigation map** — which situation requires which documents.
- A **lifecycle protocol** — Plan → Freeze → Validate → Archive sequence (mandatory).
- A **STOP protocol** — automatic halt conditions + conflict report format.
- A **milestone report template** — standard output after each milestone.

**This document is NOT:**
- A new constitution. The constitution is `docs/00_PROJECT_CONSTITUTION.md`. Do not duplicate it here.
- A new standards file. Standards live in `docs/31–49`. Do not duplicate them here.
- A new spec. Phase specs live in `docs/74`, `docs/75`, and future `docs/76+`.
- A place to invent rules. If a rule is missing, propose an ADR — do not add it silently here.

**If this document ever conflicts with a frozen freeze-doc or the Project Constitution, the frozen doc wins and this file is in error and must be corrected.**

---

## 1. Authority Ranking (THE core rule)

When any two sources conflict, resolve in this exact descending order. Higher wins. No exceptions.

| Rank | Source | Examples | Mutability |
|------|--------|----------|------------|
| 1 (highest) | User Decision / Instruction | Current developer mandate; cannot override AGENTS.md constitutional constraints | Cannot override Rank 2–4 |
| 2 | AGENTS.md (Agent Constitution) | Boot sequence, authority ranking, STOP rules, milestone protocol | ADR + human approval only |
| 3 | 60_MASTER_INDEX.md | Document locator only | ADR + human approval only |
| 4 | Phase Master Specifications | `docs/74_PHASE_1_12_*.md`, `docs/75_PHASE_13_*.md`, `docs/76_PHASE_14_*.md` (STATUS: FROZEN) | Change Request (CR) only |
| 5 | Implementation Plan | Phase 14 Revised v2 Implementation Plan (milestone breakdown) | Awaiting approval |
| 6 | Implementation (Codebase) | The code inside `api/`, `core/` | Must conform to Spec |
| 7 (lowest) | Walkthrough (History) | `walkthrough.md` (historical record only) | Non-authoritative history |

**Rank 1 — the task mandate (read carefully):** The current user instruction is the agent's mandate for *what to work on* and its scope of action. It sits at Rank 1 because it triggers all work. But it can **never authorize a violation of Rank 2–4**.
- User: "Implement Phase 15" → proceed (new scope, no frozen boundary crossed).
- User: "Modify Phase 13" → STOP. Phase 13 is frozen (rank 4). Emit a Conflict Report (§6) and wait for a Change Request (§8).

If a user instruction conflicts with a frozen source (ranks 2–4), the agent must not comply silently — it must invoke the STOP protocol (§6). A human may then authorize the change through a CR/ADR; only after such authorization may the agent proceed.

**Rank 5 — Implementation Plan Authority (execution plan only):**
Implementation Plans are execution documents. They describe *how* to implement an already approved specification (Rank 4).
They MUST NOT introduce new architecture, contracts, API shapes, invariants, or lifecycle rules.
If an Implementation Plan differs from a frozen Specification (Rank 4), the Specification wins. The implementation plan must be amended and approved before coding continues.

**Rule of application:** If you (the agent) believe a lower-ranked source should win, that is a STOP condition. Do not proceed. File a conflict report (§6).

---

## 2. Mandatory Boot Sequence

Before writing or modifying ANY code, an agent MUST complete this read sequence and present a summary of understanding.
This sequence respects the 50% context budget (`docs/10_CONTEXT_LOADING_RULES.md`).

```
BOOT
↓
Read `.ai/RESUME_STATE.md` -> If token exists, jump EXACTLY to that state
↓
Read `.ai/LOCKS.md` -> If target is locked, STOP or wait
↓
Read `.ai/CHECKPOINT.md` & `.ai/BUILD_SESSION.md` -> Know exactly where we are
↓
Read `.ai/PROJECT_STATE.md`
↓
If milestone frozen -> Do not reopen
↓
Read `.ai/CURRENT_TASK.md`
↓
Read required docs only (via `.ai/CONTEXT_INDEX.md`)
↓
Continue Exactly from Checkpoint
```

**Boot Discipline (Prohibited Expressions):**
An agent must NEVER say or assume:
- "I know."
- "I assume."
- "I'll continue."

Instead, the agent must output this structured header explicitly before executing code changes:
- **Authority Loaded:** <document paths>
- **Current Phase:** <phase number>
- **Dependencies:** <dependency info>
- **Frozen Interfaces:** <list of interfaces>
- **Files to modify:** <list of files>
- **Files prohibited:** <list of files>
- **STOP Conditions:** <applicable stop rules>
- **Waiting for approval:** (Wait for Architect approval before making code changes)

**Forbidden:** 
- Reading the entire `docs/` folder, or all of `core/**`, in one session. 
- Re-reading past milestone reports or rebuilding the entire context.
- Modifying any file NOT explicitly listed in `.ai/CURRENT_TASK.md`.
- Next Chat Boot MUST ONLY read a maximum of 10-15 state/changed files, NEVER the entire repository.

---

## 3. Situation → Context Map

| If your task is... | You MUST first read... | Then proceed under... |
|---|---|---|
| Modifying any Phase 1–13 code | `docs/74`, `docs/75`, `docs/architecture/01` | §6 STOP protocol (frozen change) |
| Adding a new Phase (14+) | The approved `docs/76_PHASE_14_*.md` spec | §5 Lifecycle |
| Adding a Pydantic DTO | `docs/33_CODE_STANDARD.md`, `docs/47_QUALITY_GATES.md` | DTO-First rule (§7.5) |
| Adding a repository class | `docs/35_DATABASE_STANDARD.md` | Repository Rule (§7.7) |
| Adding a validator/compiler/orchestrator | Phase spec + `docs/00` Rule 11 (SRP) | §7 invariants |
| Writing tests | `docs/41_TESTING_STANDARD.md`, `docs/47_QUALITY_GATES.md` | Coverage ≥ 80% (100% security) |
| Touching API layer | `docs/34_API_STANDARD.md`, `docs/architecture/02` | Layer direction (§7.4) |
| Touching secrets/permissions | `docs/26`, `docs/27`, `docs/29` | Security Agent veto applies |
| Anything in `core/security/` | `docs/26_SECURITY_CONSTITUTION.md` | Human authorization required |

---

## 4. Frozen Architecture Boundaries (pointer — do not duplicate)

These are frozen. Detail lives in the cited docs; do not restate them here.

- **System layers & dependency direction:** `docs/architecture/01_ARCHITECTURE_FREEZE.md`
  - `UI → API → Brain → {Memory, Tools}`. Lower layers never import higher layers.
- **Repository layout:** `docs/architecture/10_REPOSITORY_LAYOUT_FREEZE.md` + `docs/31_FOLDER_STRUCTURE_STANDARD.md`
- **API contracts:** `docs/architecture/02_API_CONTRACTS_FREEZE.md`
- **Database schemas:** `docs/architecture/03_DATABASE_SCHEMAS_FREEZE.md`
- **Component interfaces:** `docs/architecture/08_COMPONENT_INTERFACE_FREEZE.md`
- **Phase 1–12 baseline:** `docs/74_PHASE_1_12_MASTER_SPECIFICATION.md` (STATUS: FROZEN)
- **Phase 13 baseline:** `docs/75_PHASE_13_MASTER_SPECIFICATION.md` (STATUS: FROZEN, 187/187 tests)

To modify ANY of these, a Change Request (CR-XXX) is mandatory (see §8).

---

## 5. Implementation Lifecycle (mandatory — no step may be skipped)

```
Approved Specification (FROZEN)
        │
        ▼
Implementation Plan
        │
        ▼
Approval (human)
        │
        ▼
Task Checklist
        │
        ▼
Milestone 1  ──►  Mini Quality Gate  ──►  Approval
        │
        ▼
Milestone 2  ──►  Mini Quality Gate  ──►  Approval
        │
       ...
        │
        ▼
Milestone N  ──►  Mini Quality Gate  ──►  Approval
        │
        ▼
Final Quality Gate (full suite, no regression, coverage target)
        │
        ▼
Walkthrough
        │
        ▼
Freeze (update phase spec STATUS → FROZEN, record test count)
        │
        ▼
Freeze Validation (re-run full suite, confirm frozen interfaces unchanged)
        │
        ▼
Archive (commit with conventional message per docs/44_GIT_WORKFLOW.md)
```

### 5.1 Freeze Workflow
```
Architect Approval
        ↓
Freeze milestone
        ↓
Update `.ai/FREEZE_LEDGER.md`
        ↓
Archive report
        ↓
Update `.ai/PROJECT_STATE.md`
        ↓
STOP
```

**A "Mini Quality Gate" =** ruff format + ruff check + mypy + pytest (affected) + coverage (affected).
**The "Final Quality Gate" =** full suite + zero regression + coverage target met (§9).

No milestone may be declared complete without its gate passing AND its report (§10 format) delivered.

**Phase Completion Checklist:**
A phase cannot be marked COMPLETE until all of the following are true:
- `[ ]` Specification = Frozen
- `[ ]` Implementation Plan = Approved
- `[ ]` Walkthrough = Generated
- `[ ]` Tests ≥ Required Coverage
- `[ ]` Ruff Pass
- `[ ]` Mypy Pass
- `[ ]` Architecture Audit Pass
- `[ ]` Authority Audit Pass
- `[ ]` No STOP conditions open
- `[ ]` User Approval Recorded

---

## 6. Automatic STOP Protocol

An agent MUST halt implementation immediately and emit a Conflict Report if ANY of these occur:

**STOP Conditions:**
1. A frozen interface (§4) would need modification.
2. A circular dependency is detected between layers or modules.
3. A Repository would gain validation, planning, business logic, or execution.
4. A Compiler would gain tool execution responsibility.
5. A Validator would write to the database, execute a tool, or call an LLM.
6. An Orchestrator would bypass `ExecutionOrchestrator` or recompile a workflow.
7. The API layer would import an implementation detail incorrectly (layer reversal).
8. Two authority sources conflict (§1) and the agent cannot reconcile by ranking.
9. The approved specification and the existing code disagree.
10. A DTO required by the DTO-First rule (§7.5) does not yet exist.
11. The implementation plan deviates from or contradicts the approved Phase Specification.

**Conflict Report Format (emit this verbatim, then wait):**

```
IMPLEMENTATION BLOCKED

Reason:            <one of the 11 conditions above, stated precisely>
Affected files:    <paths>
Conflicting source: <which doc / interface / spec / plan>
Source A (e.g. Spec): <details>
Source B (e.g. Code/Plan): <details>
Impact:            <governance / architectural impact>
Recommended resolution: <your proposal — non-binding>
Authority invoked: <rank from §1>

Waiting for architect approval. Not proceeding.
```

---

## 6.1 Specification-First Resolution Rule (permanent — non-negotiable)

When an implementation conflicts with an approved frozen specification, **the implementation always loses.** An agent (or human) must NEVER rewrite a specification to match an implementation that already exists on disk. The frozen specification is the source of truth; the code is the derivative.

This rule exists precisely because of the failure mode it prevents: a divergent implementation appears on disk (via a context-rewrite, an abandoned branch, a tool, or human edits), and an agent "fixes" the contradiction by editing the spec backward to match the code. That silently retcons the architecture and destroys the meaning of "frozen." It must not happen.

**When a spec-vs-implementation conflict is detected, the only valid responses are:**

1. **Archive the implementation** (move, never delete — preserve provenance), then re-derive from the specification; OR
2. **Raise a Change Request (CR, §8)** proposing the spec change, and STOP until a human approves it. Only after CR approval may the spec be amended, and only then may code be written against the amended spec.

**Forbidden, always:**
- Editing a frozen spec to match on-disk code without an approved CR.
- Reusing, importing, or "salvaging" code from a divergent implementation into the frozen baseline.
- Adopting any authority cited in code but absent from `docs/`, `AGENTS.md`, or git history (e.g. "Invariant N", "Revision X", "Phase Y+").

**Concrete test:** If you cannot point to the line in an approved frozen document that authorizes a piece of code, treat the code as unauthorized. Cite the spec, not the code.

*Origin:* codified 2026-06-28 after a divergent Phase 14 implementation (SSE-based, citing phantom "Invariant/Gatekeeper" authority) appeared on disk and was correctly archived per this rule rather than retro-fitted into `docs/76`. See `archive/phase14_prefreeze_divergent/README.md`.

---

## 7. Per-Component Invariants (condensed pointers — see cited docs for full text)

These are the invariants the governance model rests on. They are condensed here ONLY so an agent can self-check quickly; the authoritative text is the cited frozen spec.

| # | Invariant | Authority doc |
|---|-----------|---------------|
| 7.1 | Frozen phases (1–13) are not modified without a CR. | `docs/74`, `docs/75` |
| 7.2 | The agent does not redesign architecture — it implements approved specs. | `docs/00` Pillar 5 |
| 7.3 | Every file has exactly one responsibility (SRP). | `docs/00` Pillar 11 |
| 7.4 | Dependency direction: `api/ → core/`. Never reverse. `core` never imports `api`. | `docs/architecture/01` |
| 7.5 | DTO-First ordering: DTO → Validator → Compiler → Repository → Orchestrator → Kernel → Tests. | `docs/75` §Architecture Boundary |
| 7.6 | Compiled objects, Pydantic DTOs, Enums, and frozen Specs are immutable. | `docs/75` §Invariants |
| 7.7 | Repository = CRUD + transactions + versioning + checksums ONLY. No business logic. | `docs/75` §Repository |
| 7.8 | Validator never writes DB, executes tools, or calls an LLM. | `docs/75` §Validator |
| 7.9 | Compiler never executes workflow — it only transforms. | `docs/75` §Compiler |
| 7.10 | Orchestrator coordinates; never validates, stores, recompiles, or bypasses ExecutionOrchestrator. | `docs/75` §Orchestrator |

---

## 8. Change Request (CR) Process

To modify anything in §4 or any frozen interface:

1. **Propose:** Declare `CR-XXX` with reasoning, files affected, risks, benefits.
2. **Review:** Architecture Gatekeeper reviews for SRP, immutability, and frozen-boundary compliance.
3. **Approve:** Lock updated only after explicit human Gatekeeper approval.
4. **Record:** CR appended to the affected phase spec; spec version incremented.

No agent may self-approve a CR. A CR proposal is itself a STOP-and-wait action.

---

## 9. Quality Gates (pointer — authoritative text in `docs/47_QUALITY_GATES.md`)

Every milestone gate and the final gate must satisfy:

| Gate | Tool / Command | Target |
|------|----------------|--------|
| Format | `ruff format --check` | clean |
| Lint | `ruff check` | zero errors/warnings |
| Types | `mypy` (strict) | zero errors |
| Tests | `pytest` | all pass, zero regression |
| Coverage | `pytest --cov` | ≥ 80% general, **100% security** |
| Architecture audit | dependency-cycle + layer-direction check | zero violations |
| Approval | human review | 1 approval required |

**Tooling config:** `pyproject.toml` → ruff `line-length=88, select=[E,F,W,I]`, mypy `strict=true`, pytest `asyncio_mode=auto`.

### 9.1 Verification Strategy (Incremental)
NEVER run the entire verification suite on every change. 
Use the following rule instead:
- **Changed python file?** → Run `mypy` on that file ONLY.
- **Changed formatting?** → Run `ruff` on that file ONLY.
- **Changed tests?** → Run `pytest` on that test ONLY.
- **Changed architecture?** → Run `dogfood` script.

---

## 10. Milestone Report Format

After EVERY milestone, the agent emits this report verbatim (adapted from the user's lifecycle spec). No milestone is closed without it. An agent MUST NOT proceed to the next milestone without explicit architect approval.

```
MILESTONE <N> REPORT

Completed:           <one-line summary>
Files Modified:      <paths>
Responsibilities:    <what each file now owns>
Architecture Impact: <none / additive / <CR-XXX>>
Public Interface Changes: <none / <list>>
Tests Added:         <count + paths>
Frozen modules touched: <NONE / list of modified frozen files>
Ruff:                <pass/fail>
Mypy:                <pass/fail>
Coverage:            <% for affected files>
Gate status:         PASS / BLOCKED (<reason>)

Awaiting approval before proceeding. Not proceeding.
```

---

## 11. Output Discipline

- One milestone at a time. Never batch multiple milestones into one review.
- One responsibility per change. Do not mix a refactor with a feature.
- One review at a time. Deliver, await approval, then proceed.
- Never send giant patches. If a milestone is large, split it into sub-milestones.
- Every change set must independently pass its mini quality gate.
- **Standardized Code Header:** Every implementation file must carry a docstring header at the top pointing to its specification, plan, and non-authoritative status:
  ```python
  """
  PHASE: <phase_number>
  STATUS: IMPLEMENTATION
  SPECIFICATION:
      docs/<spec_file_name>
  
  IMPLEMENTATION PLAN:
      docs/<plan_file_name>
  
  AUTHORITATIVE:
      NO
  
  DO NOT CHANGE CONTRACTS HERE.
  Contracts come only from Phase Specification.
  """
  ```

### 11.1 The Runtime-Driven Rule (Code First Policy)
To prevent agents from getting stuck in "documentation loops", the following strict rules apply to all execution:

**RULE 1: No Documentation First**
- Never start a build step by updating dashboards, roadmaps, or executive reports.
- Dashboards are the VERY LAST step of a milestone.

**RULE 2: Execution Order**
1. Code First (Python).
2. Tests Second.
3. Review Third.
4. Freeze Fourth.
5. Documentation Last (Dashboards/Roadmaps).

**RULE 3: The Code-to-Markdown Ratio**
- Milestone completion reports MUST show more Python/Test files modified than Markdown files.
- If `Markdown Modified > Python Modified`, the milestone is an automatic **FAIL** and will be rejected by the Architect.
- **Budget:** 95% Coding, 5% Documentation.

---

## 12. Phase Status Board

Maintain this board. When a phase freezes, add one line here and set its spec STATUS to FROZEN.

| Phase | Spec Doc | Status | Test Count (at freeze) |
|-------|----------|--------|------------------------|
| 1–12 | `docs/74_PHASE_1_12_MASTER_SPECIFICATION.md` | ✅ FROZEN | — (consolidated) |
| 13 | `docs/75_PHASE_13_MASTER_SPECIFICATION.md` | ✅ FROZEN (2026-06-28) | 187 passed |
| 14 | `docs/76_PHASE_14_API_GATEWAY_SPECIFICATION.md` | ✅ FROZEN (2026-06-28) | 230 passed |
| 15 | `docs/77_PHASE_15_PERSISTENT_EXECUTION_SPECIFICATION.md` | ✅ FROZEN (2026-06-29) | 265 passed |
| 16 | `AGENTS.md` | ✅ FROZEN (2026-06-29) | 193 passed |
| 17 | `docs/78_PHASE_17_AUTHENTICATION_AUTHORIZATION_SPECIFICATION.md` | ✅ FROZEN (2026-06-30) | 288 passed |
| 18 | `docs/79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md` | ✅ FROZEN (2026-06-30) | 443 passed (155 skill) |
| 19 | `docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md` | ✅ FROZEN (2026-07-04) | 179 passed |
| 20 | `(no spec, runtime built)` | ✅ FROZEN (2026-07-04) | 265 passed |
| 21 | `(no spec, runtime built)` | ✅ FROZEN (2026-07-04) | 14 passed |
| 22 | `docs/82_PHASE_22_ORCHESTRATOR_SPECIFICATION.md` | ✅ FROZEN (2026-07-04) | 907 passed |
| 23 | `docs/83_PHASE_23_TOOL_RUNTIME_SPECIFICATION.md` | ✅ FROZEN (2026-07-04) | 923 passed |
| 24 | `docs/84_PHASE_24_AUTONOMOUS_AGENT_SPECIFICATION.md` | ✅ FROZEN (2026-07-04) | 957 passed |
| 25 | `docs/86_PHASE_25_BROWSER_RUNTIME_SPECIFICATION.md` | ✅ FROZEN (2026-07-04) | 986 passed |
| 26 | `docs/87_PHASE_26_MULTI_AGENT_PERSISTENT_RECOVERY_SPECIFICATION.md` | ✅ FROZEN (2026-07-04) | 1005 passed |
| 27 | `docs/88_PHASE_27_OBSERVABILITY_COST_GOVERNANCE_SPECIFICATION.md` | ✅ FROZEN (2026-07-04) | 1055 passed |
| 28 | `docs/90_PHASE_28_SECURITY_VAULT_HARDENING_SPECIFICATION.md` | ✅ FROZEN (2026-07-04) | 1068 passed |
| 29 | `docs/91_PHASE_29_ADVANCED_VAULT_OPERATIONS_SPECIFICATION.md` | ✅ FROZEN (2026-07-04) | 1073 passed |
| 30 | `docs/92_PHASE_30_CLOUD_SYNC_HIGH_AVAILABILITY_SPECIFICATION.md` | ✅ FROZEN (2026-07-04) | 1080 passed |
| 31 | `docs/93_PHASE_31_FEDERATION_SPECIFICATION.md` | ✅ FROZEN (2026-07-05) | 1086 passed |
| 32 | `docs/94_PHASE_32_ADMINISTRATION_OPERATIONS_SPECIFICATION.md` | ✅ FROZEN (2026-07-05) | 1102 passed |
| 33 | `docs/95_PHASE_33_PRODUCTION_READINESS_SPECIFICATION.md` | ✅ FROZEN (2026-07-05) | 1115 passed |
| 34 | `docs/96_PHASE_34_AUTONOMOUS_AGENT_MISSION_SPECIFICATION.md` | ✅ FROZEN (2026-07-05) | 1126 passed |
| 35 | `docs/97_PHASE_35_DISTRIBUTED_SCALE_SPECIFICATION.md` | ✅ FROZEN (2026-07-05) | 1132 passed |
| 36 | `docs/98_PHASE_36_SWARM_INTELLIGENCE_SPECIFICATION.md` | ✅ FROZEN (2026-07-05) | 1136 passed |
| 37 | `docs/99_PHASE_37_BRAIN_KERNEL_SPECIFICATION.md` | ✅ FROZEN (2026-07-05) | 1136 passed |
| 38 | `docs/100_PHASE_38_UNIFIED_MEMORY_SPECIFICATION.md` | ✅ FROZEN (2026-07-05) | 1164 passed |
| 39 | `docs/101_PHASE_39_WORKFLOW_GRAPH_ENGINE_SPECIFICATION.md` | ✅ FROZEN (2026-07-06) | 1208 passed |
| 40 | `docs/102_PHASE_40_EVENT_BUS_REACTIVE_ARCHITECTURE_SPECIFICATION.md` | ✅ FROZEN (2026-07-06) | 1215 passed |
| 41 | `docs/103_PHASE_41_CAPABILITY_REGISTRY_SPECIFICATION.md` | ✅ FROZEN (2026-07-06) | 60 passed (1215 total) |
| 42 | `docs/104_PHASE_42_IDENTITY_ENGINE_SPECIFICATION.md` | ✅ FROZEN (2026-07-06) | 44 passed (1259 total) |
| 43 | `docs/105_PHASE_43_GOAL_ENGINE_SPECIFICATION.md` | ✅ FROZEN (2026-07-06) | (no new tests; spec freeze) |
| 44 | `docs/106_PHASE_44_MISSION_SCHEDULER_SPECIFICATION.md` | ✅ FROZEN (2026-07-06, v1.1 per CR-001 2026-07-10) | (no new tests; v1.1 amendment) |
| 45 | `docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md` (v1.2 FROZEN-amended, 2026-07-08, CR-1/2/3/4 applied) | 🔨 IN DEVELOPMENT on `phase45/transport` (M6.4.A + M6.4.B.1 + M6.4.B.2 landed; governance retrofitted 2026-07-11) | 1985 on branch (vs 1761 main baseline) |



**M5.5.1 (Architecture Linter) sub-milestone board:**

| Sub | Deliverable | Status | Tests | Approved |
|-----|------------|--------|-------|----------|
| M5.5.1.A | Skeleton (engine, registry, reporters, CLI) | ✅ APPROVED | 25 | 2026-07-03 |
| M5.5.1.B | LayerDirection rules (LR-1..5) | ✅ APPROVED | +20 (48) | 2026-07-03 |
| M5.5.1.C | Repository rules (NBR-1..4) | ✅ APPROVED | +20 (68) | 2026-07-03 |
| M5.5.1.D | Engine rules (NSD-1..3) | ✅ APPROVED | +12 (80) | 2026-07-03 |
| M5.5.1.E | DTO + UI-core rules (NDE-1..3, NUC-1..2) | ✅ APPROVED | +33 (113) | 2026-07-04 |
| M5.5.1.F | NCP + CI + KG stubs + Freeze + Dogfooding | ✅ FROZEN | +final (118) | 2026-07-04 |
| M5.5.2 | Dependency Graph Validator (DGV) | ✅ FROZEN | +61 (179) | 2026-07-04 |

> **Live tracking:** [JARVIS_EXECUTIVE_DASHBOARD.md](JARVIS_EXECUTIVE_DASHBOARD.md) is updated at every sub-milestone approval.

**Implementation Plan:** `docs/81_PHASE_19_IMPLEMENTATION_PLAN.md` — FROZEN (2026-06-30)

---

## 13. Related Documents (canonical pointers)

- Constitution: [docs/00_PROJECT_CONSTITUTION.md](docs/00_PROJECT_CONSTITUTION.md)
- Agent roles: [docs/08_AI_AGENT_CONSTITUTION.md](docs/08_AI_AGENT_CONSTITUTION.md)
- Prompt rules: [docs/09_PROMPT_CONSTITUTION.md](docs/09_PROMPT_CONSTITUTION.md)
- Context loading: [docs/10_CONTEXT_LOADING_RULES.md](docs/10_CONTEXT_LOADING_RULES.md)
- Architecture freeze: [docs/architecture/01_ARCHITECTURE_FREEZE.md](docs/architecture/01_ARCHITECTURE_FREEZE.md)
- Quality gates: [docs/47_QUALITY_GATES.md](docs/47_QUALITY_GATES.md)
- Phase 1–12 spec: [docs/74_PHASE_1_12_MASTER_SPECIFICATION.md](docs/74_PHASE_1_12_MASTER_SPECIFICATION.md)
- Phase 13 spec: [docs/75_PHASE_13_MASTER_SPECIFICATION.md](docs/75_PHASE_13_MASTER_SPECIFICATION.md)
- Master index: [docs/60_MASTER_INDEX.md](docs/60_MASTER_INDEX.md)

---

## 14. Modification Policy for THIS Document

This file may be updated by the maintainer to:
- Add a newly frozen phase to §12.
- Add a new frozen interface pointer to §4.
- Refine the situation→context map (§3).

This file may NOT be used to:
- Override any rank-1-to-6 source (§1).
- Introduce new architectural rules (use an ADR instead).
- Authorize a frozen-interface change (use a CR instead).

If this file ever contradicts a frozen doc, the frozen doc wins and this file must be corrected.
