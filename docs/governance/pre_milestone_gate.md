# Pre-Milestone Gate (PMG) — Mandatory Engineering Gate

**Status:** ✅ FROZEN — 2026-07-03 (M5.5.0)
**Version:** 1.0
**Date opened:** 2026-07-03
**Frozen by:** M5.5.0 (Engineering Governance Freeze)
**Owner:** Engineering Governance 2.0
**Authority:** AGENTS.md §5 (Implementation Lifecycle), §6 (STOP protocol)
**Binding:** Yes — applies to all milestones from Phase 19 M6 onwards.
**Related systems:**
- [architecture_review_board.md](architecture_review_board.md) — ARB
- [design_review_gate.md](design_review_gate.md) — DRG
- [threat_modeling.md](threat_modeling.md) — STRIDE
- [compatibility_matrix.md](compatibility_matrix.md)
- [engineering_decision_log.md](engineering_decision_log.md) — EDL
- [rfc_process.md](rfc_process.md)

---

## 1. Purpose

A Pre-Milestone Gate is a **mandatory checkpoint** executed **before** writing any implementation code for a milestone. It exists to prevent the failure mode observed in divergent Phase 14 attempts: writing code first, then discovering the architecture was unsound.

**Rule:** If any single item in this gate is "NO", implementation MUST NOT start. The agent emits a STOP report and waits for resolution.

---

## 2. The 12 Checkpoints

For the upcoming milestone (e.g. M6 Knowledge Graph), answer each item with **YES / NO / N/A** and attach evidence.

### 2.1 Spec frozen?

- **Question:** Is the governing Phase Specification (e.g. `docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md`) marked `STATUS: FROZEN`?
- **Evidence:** Header line + version + freeze date.
- **NO means:** Spec is in DRAFT or PROPOSED. Cannot implement against it.

### 2.2 ADR exists?

- **Question:** Is there at least one Architecture Decision Record covering the major design choices for this milestone?
- **Evidence:** File path under `docs/architecture/adrs/` with the prescribed structure (Context, Decision, Alternatives, Consequences, Future Changes).
- **NO means:** No decision history. Future agents will not understand *why* this was built this way.

### 2.3 Public interface frozen?

- **Question:** Are the public DTOs, repository interfaces, and service signatures frozen in a contract document?
- **Evidence:** Path under `docs/contracts/` with `STATUS: FROZEN` and a version.
- **NO means:** Implementation will leak internal shapes; consumers cannot be designed.

### 2.4 DTO frozen?

- **Question:** Are all DTOs that this milestone will produce or consume already defined in `core/memory/dto.py` (or domain-equivalent) with `schema_version: Literal["1.0"]` and full Pydantic validation?
- **Evidence:** Diff or pointer to the DTO file with line numbers.
- **NO means:** Violates DTO-First ordering (AGENTS.md §7.5).

### 2.5 Error contract frozen?

- **Question:** Are all custom exception types for this milestone defined in a single `errors.py` with stable names, codes, and retryability flags?
- **Evidence:** Path + table mapping each error → HTTP code (API layer) → retryable Y/N.
- **NO means:** Callers cannot write defensive code; observability cannot classify failures.

### 2.6 Event contract frozen?

- **Question:** Are all events this milestone will emit defined with topic name, payload schema, ordering guarantee, and event-bus destination?
- **Evidence:** `core/events/topics.py` entries + `core/events/schemas/` payloads.
- **NO means:** Subscribers cannot be written; event-driven flows break silently.

### 2.7 Architecture reviewed?

- **Question:** Has a Design Review Gate (DRG) been held for this milestone's layering, dependency direction, and component boundaries?
- **Evidence:** `docs/governance/drg/DRG-YYYY-NNN.md` with all 6 questions answered (Scalability, Failure recovery, Observability, Upgrade path, Rollback, Migration). See [design_review_gate.md](design_review_gate.md).
- **NO means:** Architectural drift risk. Frozen boundaries may be violated unintentionally.

### 2.8 Tests designed first?

- **Question:** Are the test cases for this milestone specified in a test plan *before* implementation? Each requirement maps to at least one test.
- **Evidence:** Path to test plan + traceability matrix.
- **NO means:** Coverage will be measured against accidental behavior, not specified behavior.

### 2.9 Rollback plan?

- **Question:** If this milestone ships and fails in production, can it be safely rolled back without data loss or downstream breakage?
- **Evidence:** Rollback steps + compatibility assessment (DB migrations backwards? feature flag toggle? dual-write strategy?).
- **NO means:** Ship = bet the company. Unacceptable for an operating system.

### 2.10 Performance budget?

- **Question:** Are p50 / p95 / p99 latency targets, throughput caps, and memory ceilings defined for every public operation in this milestone?
- **Evidence:** Path under `docs/performance/` with a budget table.
- **NO means:** No way to detect regression. "It's fast enough" is not a budget.

### 2.11 Security review?

- **Question:** Has the Security Agent reviewed this milestone for: data classification, PII handling, encryption-at-rest/in-transit, tenant isolation, audit logging, injection vectors, dependency CVEs, AND completed a STRIDE threat model?
- **Evidence:**
  - `docs/threat/TM-YYYY-NNN.md` with all 6 STRIDE categories analyzed. See [threat_modeling.md](threat_modeling.md).
  - Security review checklist with PASS/FAIL per item.
  - Residual risks list with sign-off.
- **NO means:** Unknown blast radius in a multi-tenant AI system. Security Agent veto applies.

### 2.12 Future compatibility?

- **Question:** Has the design been checked for compatibility with: (a) later milestones in the same phase, (b) later phases (Agent Runtime, Workflow, Multi-Agent), (c) external schema evolution (DTO `schema_version` field)?
- **Evidence:**
  - `docs/compatibility/CM-YYYY-NNN.md` mapping DTO v1 → Validator v1 → Repository v1 → API v1 → CLI v1. See [compatibility_matrix.md](compatibility_matrix.md).
  - Compatibility notes + versioned DTOs.
  - Engineering Decision Log entries for any deferred-compatibility decisions. See [engineering_decision_log.md](engineering_decision_log.md).
- **NO means:** Future work will require a CR. Expensive.

---

## 3. STOP Conditions Specific to This Gate

The following auto-STOP situations arise directly from a failed Pre-Milestone Gate:

1. **Spec not frozen** → STOP. You cannot implement against a moving target.
2. **No ADR** → STOP. "Why?" is the first question future maintainers will ask.
3. **DTO not frozen** → STOP. AGENTS.md §7.5 DTO-First ordering is non-negotiable.
4. **Architecture review failed** → STOP. Frozen boundaries (AGENTS.md §4) cannot be crossed silently.
5. **Security review FAIL** → STOP. Security Agent veto cannot be overridden by other reviewers.

For other NO answers, the agent may propose a remediation plan and request conditional approval. Conditional approval must be recorded in the milestone report.

---

## 4. Gate Outcomes

| Outcome | Meaning | Next Step |
|---|---|---|
| **12 / 12 YES** | Green light | Proceed with milestone |
| **≥ 9 / 12 YES, others N/A** | Proceed with caveats | Record caveats in milestone report |
| **Any NO on items 2.1, 2.2, 2.3, 2.4, 2.7, 2.11** | Hard STOP | Cannot proceed; fix the gap |
| **< 9 / 12 YES** | Soft STOP | Architect decides: remediate or defer milestone |

---

## 5. Gate Document Template (per milestone)

Before starting implementation, fill this out and attach to the milestone report.

```
PRE-MILESTONE GATE — M6.0 Knowledge Graph

□ 2.1  Spec frozen?                       YES / NO   (evidence: <link>)
□ 2.2  ADR exists?                        YES / NO   (evidence: <link>)
□ 2.3  Public interface frozen?           YES / NO   (evidence: <link>)
□ 2.4  DTO frozen?                        YES / NO   (evidence: <link>)
□ 2.5  Error contract frozen?             YES / NO   (evidence: <link>)
□ 2.6  Event contract frozen?             YES / NO   (evidence: <link>)
□ 2.7  Architecture reviewed?             YES / NO   (evidence: <link>)
□ 2.8  Tests designed first?              YES / NO   (evidence: <link>)
□ 2.9  Rollback plan?                     YES / NO   (evidence: <link>)
□ 2.10 Performance budget?                YES / NO   (evidence: <link>)
□ 2.11 Security review?                   YES / NO   (evidence: <link>)
□ 2.12 Future compatibility?             YES / NO   (evidence: <link>)

Hard STOP items (must be YES to proceed): 2.1, 2.2, 2.3, 2.4, 2.7, 2.11
Soft STOP threshold: 9/12 YES minimum.

Signed: Memory Lead / Architect / Security Agent
Date: <YYYY-MM-DD>
```

---

## 6. Relationship to Other Documents

- **AGENTS.md §5 (Implementation Lifecycle):** This gate is the gate *before* the first milestone of a phase.
- **AGENTS.md §6 (STOP Protocol):** Hard-STOP items in §3 above are specializations of the 11 generic STOP conditions.
- **AGENTS.md §9 (Quality Gates):** This gate precedes the per-milestone mini quality gate and the final quality gate.
- **AGENTS.md §10 (Milestone Report):** Gate results are reported as the first section of every milestone report.
- **Engineering Governance 2.0:** This gate is one of its deliverables. Other deliverables:
  - **ARB** ([architecture_review_board.md](architecture_review_board.md)) — answers "is this the right thing to build?"
  - **DRG** ([design_review_gate.md](design_review_gate.md)) — answers "is the design correct?"
  - **STRIDE** ([threat_modeling.md](threat_modeling.md)) — answers "what can go wrong, adversarially?"
  - **FMEA** (failure matrix in `docs/failure/`) — answers "what can go wrong, operationally?"
  - **Performance Budget** (`docs/performance/`) — defines latency/throughput targets
  - **Compatibility Matrix** ([compatibility_matrix.md](compatibility_matrix.md)) — defines version compatibility
  - **Formal Interface Contract** (`docs/contracts/`) — defines the public surface
  - **EDL** ([engineering_decision_log.md](engineering_decision_log.md)) — captures every decision
  - **RFC** ([rfc_process.md](rfc_process.md)) — meta-workflow for new phases/features

---

## 7. Versioning

- v1.0 (2026-07-03): Initial 12-checkpoint gate. Status: PROPOSED.

Future amendments require an ADR citing this file and human approval per AGENTS.md §8 (CR process).
