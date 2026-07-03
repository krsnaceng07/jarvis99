# CR-1908 — Insert M5.5 Engineering Governance Freeze into Phase 19 Plan

**Status:** ✅ APPROVED — 2026-07-03
**Date:** 2026-07-03
**Approved by:** Architect (user)
**See:** [M5.5.0 freeze report](../reports/m5_5_0_freeze_report.md)
**Type:** Plan amendment (rank 5 → rank 5)
**Affects:** [docs/81_PHASE_19_IMPLEMENTATION_PLAN.md](../81_PHASE_19_IMPLEMENTATION_PLAN.md) §2, §3
**Related:**
- [docs/phases/phase19/m5_5_engineering_governance_freeze.md](../phases/phase19/m5_5_engineering_governance_freeze.md) — full M5.5 definition
- AGENTS.md §1, §5, §8

---

## 1. Problem Statement

The Phase 19 Implementation Plan was frozen on 2026-06-30 with the milestone sequence M0–M11. Engineering Governance 2.0 was developed after the freeze (2026-07-03) and requires **13 governance documents + 6 custom tooling scripts + CI/CD pipeline** to be officially frozen and enforced before any further implementation.

If the next implementation step is M6 (Knowledge Graph), it will be written **without** the benefit of the Architecture Linter, Dependency Graph Validator, Decision Traceability checker, or Release Readiness Gate. This means:

- M6.x code may violate architectural rules that would be caught by the linter.
- M6.x decisions will not be traceable (TRACE.md will be invented ad-hoc).
- M6.x release will not have an automated RRG check.
- The governance remains "documented but unenforced" — exactly the maturity gap the user identified.

**The fix is to insert a non-code milestone — M5.5 — between M5 (Retention) and M6 (Knowledge Graph).**

---

## 2. Proposed Change

### 2.1 Insert M5.5 into the dependency chain

**Current (§2 of plan):**
```
M0 → M1 → M2 → M3 → M4 → M5 → M6 → M7 → M8 → M9 → M10 → M11
```

**Proposed:**
```
M0 → M1 → M2 → M3 → M4 → M5 → M5.5 → M6 → M7 → M8 → M9 → M10 → M11
```

### 2.2 Add M5.5 sub-milestones to §3 of plan

M5.5 is broken into 6 sub-milestones:

| Sub-milestone | Deliverable | Quality Gate |
|---|---|---|
| **M5.5.0** Governance freeze (docs) | All 13 governance docs marked `STATUS: FROZEN` with version + date | Docs review |
| **M5.5.1** Architecture Linter | `scripts/architecture_linter.py` working; all 30+ rules pass on M5 codebase; ≥ 90% test coverage | ruff + mypy + pytest |
| **M5.5.2** Dependency Graph Validator | `scripts/dgv.py` working; graph rendered; no cycles detected; ≥ 90% test coverage | ruff + mypy + pytest |
| **M5.5.3** Traceability + Governance Checkers | `scripts/trace_check.py` + `scripts/governance_check.py` working; CI integration tested | ruff + mypy + pytest |
| **M5.5.4** CI/CD Pipeline + Branch Protection | `.github/workflows/ci.yml` with 15 stages; branch protection enabled; full M5 test suite runs green | Pipeline runs end-to-end |
| **M5.5.5** M5.5 Freeze | All artifacts FROZEN; M5.5 Master Report generated; status updated in AGENTS.md §12 (proposed) | RRG (8 items) all PASS |

### 2.3 Add M5.5 to §4 Architecture Boundaries (plan)

No change to architecture boundaries. M5.5 is a meta-milestone that creates tools, not components.

### 2.4 Add M5.5 to §6 Frozen Interfaces (plan)

No change. M5.5 does not introduce new public interfaces in `core/`.

### 2.5 No change to the spec (rank 4)

The Phase 19 spec (`docs/80`) is **NOT** modified. M5.5 is a plan-level insertion, not a spec-level change.

---

## 3. Effects

### 3.1 On Phase 19

- Phase 19 plan gains 6 sub-milestones (M5.5.0 – M5.5.5) between M5 and M6.
- Total milestone count for Phase 19: 12 (M0–M11) → 18 (M0–M11, with M5.5 expanded).
- Plan version: 1.0 → 1.1 (minor bump — additive, non-breaking).

### 3.2 On M6 (Knowledge Graph)

- M6.0 inherits the 13 governance docs as binding.
- M6.0 DTOs must use the Architecture Linter to validate layer direction.
- M6.x implementation must use the Decision Traceability system (every new public symbol gets a TRACE-ID).
- M6.x CI must pass the 9 QGE gates on every commit.
- M6.9 Freeze must pass the 8-item RRG.

### 3.3 On future phases (Phase 20+)

- All future phases inherit the same governance.
- RFC process becomes mandatory for any new phase.
- M5.5 is a one-time investment; future phases get the tooling for free.

---

## 4. Backward Compatibility

- **Plan version:** 1.0 → 1.1. Additive — no existing milestone is removed or modified.
- **Existing milestones (M0–M5):** Unchanged. Their tests still pass.
- **Spec:** Unchanged. The spec is rank 4 and is NOT modified by this CR.
- **Existing governance docs (AGENTS.md, etc.):** Unchanged. M5.5 produces *new* governance docs that complement (not replace) AGENTS.md.

---

## 5. Required Approvals

Per AGENTS.md §1 (Authority Ranking): a plan amendment (rank 5) is approved by the architect (rank 1). The spec (rank 4) is not affected.

| Role | Approval | Status |
|---|---|---|
| **Architect (user)** | Approve / Reject | ⏳ PENDING |
| **Memory Lead** | (post-architect) | ⏳ PENDING |
| **Engineering Governance Lead** | (post-architect) | ⏳ PENDING |

No agent may self-approve.

---

## 6. Decision Recording

Once approved:

```
APPROVED ON: <YYYY-MM-DD>
PLAN VER:    1.0 → 1.1
NEW MILESTONES: M5.5.0, M5.5.1, M5.5.2, M5.5.3, M5.5.4, M5.5.5
ARCHITECT:   <name>
```

---

## 7. STOP Condition Active

M6.0 implementation is BLOCKED on the resolution of:
1. **CR-1907** (KG type set) — [CR-1907](../contracts/CR-1907-Knowledge-Graph-Types.md)
2. **CR-1908** (this CR — M5.5 insertion) — must be approved before M5.5 sub-milestones begin

---

## 8. Versioning

- v1.0 (2026-07-03): CR-1908 opened. Status: PROPOSED.
