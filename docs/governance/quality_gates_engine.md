# Quality Gates Engine (QGE) — Governance System

**Status:** ✅ FROZEN — 2026-07-03 (M5.5.0)
**Version:** 1.0
**Date opened:** 2026-07-03
**Frozen by:** M5.5.0 (Engineering Governance Freeze)
**Authority:** AGENTS.md §9 (Quality Gates), Engineering Governance 2.0
**Related:** Pre-Milestone Gate, Architecture Linter, Dependency Graph Validator, Release Readiness Gate, CI/CD Pipeline

---

## 1. Purpose

The Quality Gates Engine (QGE) is the **automated verification layer** that runs on every commit and every milestone. It enforces that the 8 engineering systems (ARB, DRG, STRIDE, FMEA, Performance Budget, Compatibility Matrix, Interface Contract, EDL) translate into machine-checkable rules.

**Rule:** Every commit MUST pass the QGE. Every milestone MUST pass the QGE milestone-gate configuration. There is **no manual bypass** (see §6).

---

## 2. Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                       QGE Orchestrator                        │
│  (single Python entry point, runs in CI)                      │
└────────────┬─────────────────────────────────────────────────┘
             │
   ┌─────────┼─────────┬─────────┬──────────┬──────────┐
   ▼         ▼         ▼         ▼          ▼          ▼
┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐  ┌──────────┐ ┌────────┐
│Ruff  │ │Mypy  │ │Pytest│ │Cove- │  │Arch-     │ │Security│
│Format│ │Strict│ │Suite │ │rage  │  │Linter    │ │Scan    │
│      │ │      │ │      │ │      │  │          │ │        │
└──────┘ └──────┘ └──────┘ └──────┘  └──────────┘ └────────┘
   ┌──────┐ ┌──────┐ ┌──────────────┐
   │Perf  │ │Compat│ │Documentation │
   │Budget│ │Matrix│ │Check         │
   └──────┘ └──────┘ └──────────────┘
```

Each gate is a **pluggable Python function** with signature `(repo_path: Path, config: dict) -> GateResult`.

---

## 3. The 9 Mandatory Gates

### 3.1 Architecture Gate (Gate 1)

- **Checks:** Layer direction, no cycles, no forbidden imports (per [architecture_linter.md](architecture_linter.md)).
- **Tool:** Custom `architecture_linter.py` script.
- **Threshold:** Zero violations.
- **Failure effect:** Block merge.

### 3.2 Test Gate (Gate 2)

- **Checks:** `pytest` runs, all tests pass, no skipped tests in core paths.
- **Tool:** `pytest --strict-markers --strict-config`.
- **Threshold:** 100% of declared tests pass; zero `xfail` without justification.
- **Failure effect:** Block merge.

### 3.3 Coverage Gate (Gate 3)

- **Checks:** Line + branch coverage.
- **Tool:** `pytest --cov=core --cov=api --cov-branch`.
- **Threshold:**
  - General code: ≥ 80%
  - `core/security/**`: 100%
  - New code in this milestone: ≥ 90%
- **Failure effect:** Block merge.

### 3.4 Security Gate (Gate 4)

- **Checks:** STRIDE-derived test cases all pass; dependency CVEs scanned.
- **Tool:** Custom STRIDE test runner (`tests/security/test_stride_*.py`) + `pip-audit` + `safety`.
- **Threshold:** Zero security test failures; zero HIGH/CRITICAL CVEs.
- **Failure effect:** Block merge; Security Agent notified.

### 3.5 Performance Gate (Gate 5)

- **Checks:** p95 latency per performance budget; throughput within range.
- **Tool:** `pytest-benchmark` + custom load test scripts.
- **Threshold:** p95 ≤ budget; throughput ≥ minimum.
- **Failure effect:** Block merge if regression > 10% vs. baseline.

### 3.6 Compatibility Gate (Gate 6)

- **Checks:** All public DTOs, Repository, Service, API, CLI maintain backward compatibility (per [compatibility_matrix.md](compatibility_matrix.md)).
- **Tool:** Custom compatibility linter + DTO schema diff.
- **Threshold:** No MAJOR-version breaking changes without an approved CR.
- **Failure effect:** Block merge; CR required.

### 3.7 Documentation Gate (Gate 7)

- **Checks:** Every public module has a docstring; every public DTO/function is in the docs; CHANGELOG updated.
- **Tool:** `interrogate` (docstring coverage) + custom doc-coverage check.
- **Threshold:** Docstring coverage ≥ 95% on public APIs; no undocumented public symbols.
- **Failure effect:** Block merge.

### 3.8 Dependency Gate (Gate 8)

- **Checks:** No new dependency without a `requirements-justification.md` entry; no GPL/AGPL in a proprietary product; no unmaintained packages.
- **Tool:** `pip-licenses` + `pip-audit` + custom check.
- **Threshold:** All new dependencies documented; zero GPL deps; zero unmaintained (no commits in 12 months).
- **Failure effect:** Block merge.

### 3.9 Governance Gate (Gate 9)

- **Checks:** All required governance artifacts exist and are up-to-date for the changed scope (ARB, DRG, STRIDE, FMEA, EDL entries, ADR updates).
- **Tool:** Custom governance validator (`scripts/governance_check.py`).
- **Threshold:** Zero missing artifacts; all sign-offs present.
- **Failure effect:** Block merge.

---

## 4. Gate Result Schema

Every gate returns:

```python
class GateResult(BaseModel):
    gate_id: str  # "G1-architecture", "G2-test", etc.
    status: Literal["pass", "fail", "warn", "skip"]
    score: Optional[float] = None  # 0.0–1.0; e.g. coverage = 0.94
    threshold: Optional[float] = None
    violations: List[str] = []  # human-readable failure list
    duration_ms: float
    timestamp: datetime
```

The QGE aggregates all 9 results and produces a single PASS/FAIL for the commit/milestone.

---

## 5. Per-Stage Configuration

| Stage | Gates Active | Severity |
|---|---|---|
| **Pre-commit (local)** | G1, G2, G3, G7 | Block commit |
| **CI on PR** | All 9 | Block merge |
| **Pre-milestone** | All 9 + manual sign-off | Block milestone freeze |
| **Pre-release** | All 9 + release-readiness (see §5 of [release_readiness_gate.md](release_readiness_gate.md)) | Block release tag |

---

## 6. No Manual Bypass

Manual bypass is **forbidden** by AGENTS.md §1 (Authority Ranking). If a gate fails:

1. Fix the code to make it pass.
2. If the gate is wrong, open a CR to change the gate definition.
3. If the threshold is wrong, open a CR to change the threshold.

There is no `--force-merge` flag. There is no "I'll fix it later" waiver. The CI is the contract.

---

## 7. QGE for M6 (Knowledge Graph)

The M6 milestone configuration activates the following specialized checks on top of the standard 9:

- G1: KG layer direction (no `api/` importing `core/memory/kg/`).
- G2: 10 sub-contract tests pass (§13.1–§13.10 of [KG contract](../contracts/knowledge_graph_contract.md)).
- G3: Coverage of `core/memory/kg/` ≥ 90%; `core/memory/kg/inference_engine.py` 100%.
- G4: All STRIDE TM-2026-001 tests pass.
- G5: KG performance budget (p95 latency) met at 10K nodes / 50K edges.
- G6: `KGNode`, `KGEdge`, `KGNodeType`, `KGEdgeType` schema unchanged unless CR.
- G7: All KG modules have docstring headers; all public methods documented.
- G8: New deps (e.g. `asyncpg` or `sqlalchemy[asyncio]`) justified in `requirements-justification.md`.
- G9: ARB-2026-001, DRG-2026-001, TM-2026-001 all signed.

---

## 8. Versioning

- v1.0 (2026-07-03): QGE introduced. 9 mandatory gates defined.
