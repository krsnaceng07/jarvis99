# M6 Knowledge Graph — Master Checklist

**Status:** ACTIVE (this is the single reference for "is M6 ready to code?")
**Date:** 2026-07-03
**Owner:** Memory Lead
**Subsystem:** Knowledge Graph (Phase 19, M6.0 – M6.9)
**Prerequisite:** M5.5 — Engineering Governance Freeze (must be FROZEN)

---

## 0. How to Use This Checklist

Every item in this checklist is **mandatory**. Items are grouped by:
- **A. Authority** — Spec, CRs, Governance (must be resolved BEFORE any code)
- **B. Architecture Governance** — ARB, DRG, STRIDE, FMEA, Performance, Compatibility, Interface Contract, EDL
- **C. Implementation Plan** — milestones, dependencies, rollback
- **D. Test Plan** — designed before code
- **E. M6.x Sub-milestones** — per-milestone deliverables

The Pre-Milestone Gate (12 checkpoints) and the per-milestone mini quality gate are applied at each M6.x sub-milestone.

**⚠️ M6.0 cannot start until [M5.5](../phases/phase19/m5_5_engineering_governance_freeze.md) is FROZEN.**

---

## A. Authority (BEFORE any code)

| # | Item | Status | Evidence |
|---|---|---|---|
| A0 | **M5.5 — Engineering Governance Freeze** complete | ⏳ PENDING | [M5.5](../phases/phase19/m5_5_engineering_governance_freeze.md) — must freeze 13 governance docs + tooling before M6 |
| A1 | Phase 19 spec frozen | ✅ DONE (2026-06-30) | [docs/80 §16.5/§16.6](../80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md) |
| A2 | Phase 19 implementation plan frozen | ✅ DONE (2026-06-30) | [docs/81](../81_PHASE_19_IMPLEMENTATION_PLAN.md) |
| A3 | CR-1907 resolved (KG type set: A/B/C) | ⏳ BLOCKED | [CR-1907](../contracts/CR-1907-Knowledge-Graph-Types.md) |
| A4 | Engineering Governance 2.0 ratified | ✅ DONE (2026-07-03) | [pre_milestone_gate.md](../governance/pre_milestone_gate.md) + 13 governance files |

---

## B. Architecture Governance (BEFORE M6.0 code)

| # | Item | Status | Evidence |
|---|---|---|---|
| B1 | **ARB-2026-001** filed and approved | ⏳ PENDING | [ARB-2026-001](../governance/architecture_review_board.md#7-arb-2026-001--knowledge-graph-subsystem-m6) |
| B2 | **DRG-2026-001** filed and passed (6 questions) | ⏳ PENDING | [DRG-2026-001](../governance/design_review_gate.md#6-drg-2026-001--knowledge-graph-m6-design) |
| B3 | **TM-2026-001** STRIDE filed and Security Agent sign-off | ⏳ PENDING | [TM-2026-001](../governance/threat_modeling.md#4-tm-2026-001--knowledge-graph-m6) |
| B4 | **FMEA** (failure matrix) reviewed | ✅ DONE (2026-07-03) | [knowledge_graph_failure_matrix.md](../failure/knowledge_graph_failure_matrix.md) — 17 failure modes |
| B5 | **Performance Budget** defined | ✅ DONE (2026-07-03) | [knowledge_graph_performance_budget.md](../performance/knowledge_graph_performance_budget.md) |
| B6 | **Compatibility Matrix CM-2026-001** filed | ⏳ PENDING | [CM-2026-001](../governance/compatibility_matrix.md#5-cm-2026-001--knowledge-graph-m6-compatibility-matrix) |
| B7 | **Formal Interface Contract** frozen (10-field) | 🟡 DRAFT v0.2 | [knowledge_graph_contract.md](../contracts/knowledge_graph_contract.md) §3.4 |
| B8 | **EDL sub-log opened** for M6 decisions | ✅ DONE | [EDL-M6-001 to 006](../governance/engineering_decision_log.md#5-edl-2026--knowledge-graph-m6-decisions) |
| B9 | **ADR-005 (KG)** filed | ✅ DONE (2026-07-03) | [ADR-005](../architecture/adrs/ADR-005-knowledge-graph.md) |
| B10 | **Observability Contract** defined | ✅ DONE (2026-07-03) | [knowledge_graph_observability_contract.md](../observability/knowledge_graph_observability_contract.md) |

**B-Block can only be unblocked by you (architect) approving the 4 ⏳ items.**

---

## C. Implementation Plan

| # | Item | Status | Notes |
|---|---|---|---|
| C1 | M6.0 DTO — KGNode, KGEdge, all enums frozen | ⏳ BLOCKED on CR-1907 | Use spec §16.5/§16.6 (8+7) by default |
| C2 | M6.1 Validator — KGValidator with 10-field checks | ⏳ BLOCKED on B-Block | |
| C3 | M6.2 Repository — IKGRepository impl + 9 indexes | ⏳ BLOCKED on C2 | |
| C4 | M6.3 Traversal — TraversalEngine (cycle-safe) | ⏳ BLOCKED on C3 | |
| C5 | M6.4 Inference — InferenceEngine (opt-in, bounded) | ⏳ BLOCKED on C4 | |
| C6 | M6.5 Merge — `KGService.merge_nodes()` with 5-step algorithm | ⏳ BLOCKED on C5 | |
| C7 | M6.6 Events — 10 event topics, at-least-once, PII-stripped | ⏳ BLOCKED on C6 | |
| C8 | M6.7 Integration — Memory Orchestrator consumes KG | ⏳ BLOCKED on C7 | |
| C9 | M6.8 Performance — p50/p95/p99 measured at 10K nodes | ⏳ BLOCKED on C8 | |
| C10 | M6.9 Freeze — all artifacts FROZEN, status update | ⏳ BLOCKED on C9 | |

**Dependency:** C-Block is fully serial. B-Block must clear before C1.

---

## D. Test Plan (designed before code)

| # | Item | Status | Notes |
|---|---|---|---|
| D1 | 10 sub-contract tests (§13.1–§13.10, one per sub-contract) | ⏳ NOT-STARTED | |
| D2 | 9 latency target tests (§6, one per operation) | ⏳ NOT-STARTED | |
| D3 | 9 error type tests (§5, one per error) | ⏳ NOT-STARTED | |
| D4 | 10 event topic tests (§13.8, one per topic) | ⏳ NOT-STARTED | |
| D5 | 17 FMEA tests (one per failure mode) | ⏳ NOT-STARTED | |
| D6 | 12 STRIDE tests (from TM-2026-001) | ⏳ NOT-STARTED | |
| D7 | 11 forbidden-dependency tests (architecture audit) | ⏳ NOT-STARTED | |
| D8 | Idempotency tests (create_node, create_edge) | ⏳ NOT-STARTED | |
| D9 | Concurrency tests (optimistic version conflict) | ⏳ NOT-STARTED | |
| D10 | Cycle-traversal test (visitors-set correctness) | ⏳ NOT-STARTED | |

**Total tests expected for M6:** ~100 (≥80% coverage target per AGENTS.md §9, 100% for security per governance).

---

## E. M6.x Sub-Milestones — Per-Milestone Pre-Milestone Gate

Each sub-milestone (M6.0 – M6.9) must pass the **Pre-Milestone Gate** before its code is written. The gate is summarized here; the full 12 checkpoints are in [pre_milestone_gate.md](../governance/pre_milestone_gate.md).

| Sub-milestone | PMG Required? | Mini Quality Gate? | Final Gate? | Approval |
|---|---|---|---|---|
| M6.0 DTOs | YES (all 12) | YES (ruff + mypy + pytest) | NO | Architect + Memory Lead |
| M6.1 Validator | YES (subset) | YES | NO | Memory Lead + 1 senior |
| M6.2 Repository | YES (subset) | YES | NO | Memory Lead + 1 senior |
| M6.3 Traversal | YES (subset) | YES | NO | Memory Lead + 1 senior |
| M6.4 Inference | YES (subset + DRG re-eval) | YES | NO | Architect + Security |
| M6.5 Merge | YES (subset) | YES | NO | Memory Lead + 1 senior |
| M6.6 Events | YES (subset) | YES | NO | Memory Lead + 1 senior |
| M6.7 Integration | YES (subset) | YES | NO | Architect + Memory Lead |
| M6.8 Performance | YES (subset) | YES | NO | Architect |
| **M6.9 Freeze** | **YES (full 12)** | **YES (full suite)** | **YES (full suite + zero regression + coverage)** | **Architect + Memory Lead + Security** |

---

## F. STOP Conditions (active for M6)

Per AGENTS.md §6, the following are auto-STOP for any M6.x sub-milestone:

1. CR-1907 unresolved (A3) — **CURRENTLY BLOCKED**
2. Any ARB/DRG/STRIDE item rejected (B1, B2, B3)
3. Frozen interface modified without CR
4. Repository gains validation/planning/business logic
5. Inference writes to the database
6. Validator executes tools or calls LLM
7. Layer direction violation (api/ importing from core/memory/kg/)
8. Spec-vs-implementation divergence
9. DTO-First rule violated (code written before DTOs frozen)
10. PMG fails for a sub-milestone

---

## G. Sign-off Block

```
M6 Knowledge Graph — Master Checklist Approval

I have reviewed all items above and authorize M6.0 implementation to begin.

Architect:     ___________________  Date: __________
Memory Lead:   ___________________  Date: __________
Security:      ___________________  Date: __________
```

**Until this block is signed, M6.0 implementation is BLOCKED.**

---

## H. Change Log

- 2026-07-03: Initial master checklist created. B-Block has 4 PENDING items. A3 (CR-1907) is the root blocker.
