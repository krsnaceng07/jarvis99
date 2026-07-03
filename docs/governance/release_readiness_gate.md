# Release Readiness Gate (RRG) — Governance System

**Status:** ✅ FROZEN — 2026-07-03 (M5.5.0)
**Version:** 1.0
**Date opened:** 2026-07-03
**Frozen by:** M5.5.0 (Engineering Governance Freeze)
**Authority:** AGENTS.md §9 (Quality Gates), §10 (Milestone Report), §5 (Implementation Lifecycle — "Freeze")
**Related:** Quality Gates Engine, Architecture Linter, Pre-Milestone Gate, EDL, Compatibility Matrix

---

## 1. Purpose

The Release Readiness Gate (RRG) is the **final automated check** before any release tag (a frozen milestone, a frozen phase, or a production deployment). It is the last line of defense against shipping an incomplete or broken artifact.

**Rule:** A release tag MUST NOT be created until all 8 RRG items pass. There is no emergency release override (per [quality_gates_engine.md §6](quality_gates_engine.md#6-no-manual-bypass)).

---

## 2. The 8 RRG Items

### 2.1 Architecture PASS

- **Check:** QGE Gate 1 (Architecture) passes with zero violations.
- **Evidence:** CI log + Architecture Linter report.
- **Tool:** `python -m scripts.architecture_linter`.
- **Threshold:** Zero ERROR; ≤ 5 WARN (must have justification).

### 2.2 Security PASS

- **Check:** QGE Gate 4 (Security) passes; STRIDE tests for the changed scope all pass; zero HIGH/CRITICAL CVEs in dependencies.
- **Evidence:** Security Agent sign-off + `pip-audit` + `safety` output.
- **Threshold:** Zero STRIDE test failures; zero HIGH/CRITICAL CVEs.
- **Veto:** Security Agent can veto a release even if all other gates pass.

### 2.3 Coverage ≥ 96%

- **Check:** Line + branch coverage for the released scope.
- **Threshold:**
  - General: ≥ 80% (per AGENTS.md §9)
  - **For release tag: ≥ 96%** (stricter than merge gate)
  - `core/security/**`: 100% always
- **Evidence:** `pytest --cov` HTML report committed to `docs/reports/coverage_<tag>.html`.

### 2.4 Performance PASS

- **Check:** p95 latency per Performance Budget met on the released scope.
- **Threshold:** All p95 ≤ budget; no regression > 5% vs. previous release.
- **Evidence:** Load test report in `docs/reports/perf_<tag>.md`.

### 2.5 Observability PASS

- **Check:** All operations emit metrics, logs, traces, and events as specified in the Observability Contract.
- **Threshold:** 100% of public operations have at least one of {metric, log, trace, event}.
- **Evidence:** Observability Contract check + dashboard screenshot.

### 2.6 Compatibility PASS

- **Check:** Compatibility Matrix verified; no MAJOR-version breaking changes without an approved CR; DTO schema diffs reviewed.
- **Threshold:** All MINOR-version bumps have migration notes; no unannounced MAJOR bumps.
- **Evidence:** Compatibility matrix entry signed.

### 2.7 Rollback PASS

- **Check:** A rollback runbook exists and has been **executed successfully** in a staging environment within the last 30 days.
- **Threshold:** Rollback dry-run passes; rollback completion time ≤ 15 minutes.
- **Evidence:** Staging rollback log + runbook link.

### 2.8 Documentation PASS

- **Check:** All public APIs documented; CHANGELOG updated; release notes generated; ADR + EDL up-to-date.
- **Threshold:** Docstring coverage ≥ 95%; CHANGELOG entry for this release; release notes in `docs/releases/<tag>.md`.
- **Evidence:** `interrogate` output + CHANGELOG diff.

---

## 3. RRG Workflow

```
Milestone or Phase complete
        ↓
Run all 9 QGE gates
        ↓
Run 8 RRG items (some overlap with QGE)
        ↓
If all PASS → generate release tag
If any FAIL → STOP, fix, re-run
        ↓
Tag created (e.g. v0.19.0-M6)
        ↓
Update AGENTS.md Phase Status Board
```

---

## 4. Release Tag Format

- **Phase milestone tag:** `v0.<phase>.<milestone>` (e.g. `v0.19.6` for Phase 19 M6)
- **Phase freeze tag:** `v0.<phase>.0` (e.g. `v0.19.0` for Phase 19 complete)
- **Production tag:** `v<major>.<minor>.<patch>` (e.g. `v1.0.0`)

---

## 5. RRG Sign-off

```markdown
## Release Readiness Gate — <tag>

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | Architecture | PASS / FAIL | <link> |
| 2 | Security | PASS / FAIL | <link> |
| 3 | Coverage (≥96%) | PASS / FAIL | <link> |
| 4 | Performance | PASS / FAIL | <link> |
| 5 | Observability | PASS / FAIL | <link> |
| 6 | Compatibility | PASS / FAIL | <link> |
| 7 | Rollback | PASS / FAIL | <link> |
| 8 | Documentation | PASS / FAIL | <link> |

## Sign-off
| Role | Name | Date |
|---|---|---|
| Architect | | |
| Memory Lead | | |
| Security Agent | | |

## Result
**RELEASE READY** (all PASS) / **RELEASE BLOCKED** (any FAIL)
```

---

## 6. RRG for M6 (Knowledge Graph)

When M6.9 (Freeze) completes, the RRG runs with:

- **Architecture:** KG layer direction + no cycles (DGV).
- **Security:** All 12 STRIDE TM-2026-001 tests pass.
- **Coverage:** `core/memory/kg/**` ≥ 96%; `core/memory/kg/inference_engine.py` 100%.
- **Performance:** p95 latency at 10K nodes / 50K edges within budget.
- **Observability:** All 10 KG event topics emit; metrics for create/read/traversal.
- **Compatibility:** KG DTOs v1.0 frozen; downstream consumers (Memory Orchestrator) accept the contract.
- **Rollback:** Feature flag `kg.enabled` allows toggle-off; `kg_nodes` / `kg_edges` migrations are reversible.
- **Documentation:** KG contract v1.0 frozen; ADR-005 finalized; EDL-M6 entries closed.

---

## 7. Versioning

- v1.0 (2026-07-03): RRG introduced. 8 items, sign-off workflow, M6-specific gate.
