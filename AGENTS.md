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
| 0 | Current approved user instruction | The developer's task directive for THIS session (what to work on) | Cannot override ranks 1–6 |
| 1 (highest authority) | Project Constitution | `docs/00_PROJECT_CONSTITUTION.md` (15 Pillars) | ADR + human approval only |
| 2 | Architecture Freeze Docs | `docs/architecture/01–14_*.md` | ADR + human approval only |
| 3 | Phase Master Specifications | `docs/74_PHASE_1_12_*.md`, `docs/75_PHASE_13_*.md` (STATUS: FROZEN) | Change Request (CR) only |
| 4 | Policy & Standards Docs | `docs/26–49_*.md` | ADR |
| 5 | Reference Architecture Docs | `docs/05–24_*.md` | ADR |
| 6 | Existing Code (frozen phases) | `core/**` for Phases 1–13 | CR if interface change |
| 7 | This document (AGENTS.md) | navigation + lifecycle | maintainer update |
| 8 (lowest) | Agent's own judgment | — | never override ranks 0–6 |

**Rank 0 — the task mandate (read carefully):** The current user instruction is the agent's mandate for *what to work on* and its scope of action. It sits at Rank 0 because it triggers all work. But it can **never authorize a violation of ranks 1–6**.
- User: "Implement Phase 14" → proceed (new scope, no frozen boundary crossed).
- User: "Modify Phase 13" → STOP. Phase 13 is frozen (rank 3). Emit a Conflict Report (§6) and wait for a Change Request (§8).

If a user instruction conflicts with a frozen source (ranks 1–6), the agent must not comply silently — it must invoke the STOP protocol (§6). A human may then authorize the change through a CR/ADR; only after such authorization may the agent proceed.

**Rule of application:** If you (the agent) believe a lower-ranked source should win, that is a STOP condition. Do not proceed. File a conflict report (§6).

---

## 2. Mandatory Boot Sequence

Before writing or modifying ANY code, an agent MUST complete this read sequence.
This sequence respects the 50% context budget (`docs/10_CONTEXT_LOADING_RULES.md`).

```
Step 1 (ALWAYS):  Read this file (AGENTS.md) — you are here.
Step 2 (ALWAYS):  Read docs/00_PROJECT_CONSTITUTION.md (15 Pillars).
Step 3 (ALWAYS):  Read docs/74_PHASE_1_12_MASTER_SPECIFICATION.md header + §status only.
                  (Do NOT read full body unless modifying Phases 1–12.)
Step 4 (CONTEXTUAL): Read ONLY the spec(s) for the phase you are touching:
                  - Phase 13 work → docs/75_PHASE_13_MASTER_SPECIFICATION.md
                  - Phase 14+    → docs/76_PHASE_14_*.md (when it exists)
Step 5 (CONTEXTUAL): Read ONLY the standards relevant to the file type you touch:
                  - DB work     → docs/35_DATABASE_STANDARD.md
                  - API work    → docs/34_API_STANDARD.md
                  - Tests       → docs/41_TESTING_STANDARD.md
                  - Code style  → docs/33_CODE_STANDARD.md
Step 6 (TARGETED): Read the specific source files you will modify. Never read whole packages.
```

**Forbidden:** Reading the entire `docs/` folder, or all of `core/**`, in one session. (Violates Rule 1 Pillar + Context Budget Rule.)

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

**A "Mini Quality Gate" =** ruff format + ruff check + mypy + pytest (affected) + coverage (affected).
**The "Final Quality Gate" =** full suite + zero regression + coverage target met (§9).

No milestone may be declared complete without its gate passing AND its report (§10 format) delivered.

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

**Conflict Report Format (emit this verbatim, then wait):**

```
IMPLEMENTATION BLOCKED

Reason:            <one of the 10 conditions above, stated precisely>
Affected files:    <paths>
Conflicting source: <which doc / interface / spec>
Recommended resolution: <your proposal — non-binding>
Authority invoked: <rank from §1>

Waiting for architect approval. Not proceeding.
```

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

---

## 10. Milestone Report Format

After EVERY milestone, the agent emits this report verbatim (adapted from the user's lifecycle spec). No milestone is closed without it.

```
MILESTONE <N> REPORT

Completed:           <one-line summary>
Files Modified:      <paths>
Responsibilities:    <what each file now owns>
Architecture Impact: <none / additive / <CR-XXX>>
Public Interface Changes: <none / <list>>
Tests Added:         <count + paths>
Ruff:                <pass/fail>
Mypy:                <pass/fail>
Coverage:            <% for affected files>
Next Milestone:      <what comes next, or "Final Gate">

Gate status: PASS / BLOCKED (<reason>)
```

---

## 11. Output Discipline

- One milestone at a time. Never batch multiple milestones into one review.
- One responsibility per change. Do not mix a refactor with a feature.
- One review at a time. Deliver, await approval, then proceed.
- Never send giant patches. If a milestone is large, split it into sub-milestones.
- Every change set must independently pass its mini quality gate.

---

## 12. Phase Status Board

Maintain this board. When a phase freezes, add one line here and set its spec STATUS to FROZEN.

| Phase | Spec Doc | Status | Test Count (at freeze) |
|-------|----------|--------|------------------------|
| 1–12 | `docs/74_PHASE_1_12_MASTER_SPECIFICATION.md` | ✅ FROZEN | — (consolidated) |
| 13 | `docs/75_PHASE_13_MASTER_SPECIFICATION.md` | ✅ FROZEN (2026-06-28) | 187 passed |
| 14 | `docs/76_PHASE_14_*.md` | ⬜ Not started | — |
| ... | ... | ... | ... |

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
