# CI/CD Pipeline — Continuous Quality Gates (Stage 4)

**Status:** ✅ FROZEN — 2026-07-03 (M5.5.0)
**Version:** 1.0
**Date opened:** 2026-07-03
**Frozen by:** M5.5.0 (Engineering Governance Freeze)
**Authority:** AGENTS.md §9 (Quality Gates), Engineering Governance 2.0
**Related:** Quality Gates Engine, Architecture Linter, Dependency Graph Validator, Release Readiness Gate

---

## 1. Purpose

The CI/CD pipeline is the **automation layer** that runs the 9 QGE gates on every commit and every PR. It exists to make the engineering systems *enforced*, not optional.

**Rule:** A commit cannot be merged to `main` until all gates pass. A release tag cannot be created until the Release Readiness Gate passes.

---

## 2. Pipeline Stages (per commit / per PR)

```
[1] Checkout
   ↓
[2] Setup (Python 3.11+, install deps, cache)
   ↓
[3] Lint (ruff check)
   ↓
[4] Format (ruff format --check)
   ↓
[5] Type Check (mypy --strict)
   ↓
[6] Unit Tests (pytest -m unit)
   ↓
[7] Integration Tests (pytest -m integration)
   ↓
[8] Architecture Rules (architecture_linter.py)
   ↓
[9] Dependency Graph (dgv.py)
   ↓
[10] Security Scan (pip-audit, safety, STRIDE tests)
   ↓
[11] Performance Budget (pytest-benchmark, regression check)
   ↓
[12] Coverage (pytest --cov, threshold check)
   ↓
[13] Documentation Check (interrogate, doc coverage)
   ↓
[14] Decision Traceability (TRACE.md validation)
   ↓
[15] Governance Artifact Check (ARB, DRG, STRIDE, EDL present)
   ↓
[16] Merge Gate
```

Each stage is a hard gate. Any failure blocks the merge.

---

## 3. Tooling per Stage

| # | Stage | Tool | Command | Threshold |
|---|---|---|---|---|
| 3 | Lint | ruff | `ruff check .` | Zero errors/warnings |
| 4 | Format | ruff | `ruff format --check .` | Clean |
| 5 | Type Check | mypy | `mypy --strict core/ api/` | Zero errors |
| 6 | Unit Tests | pytest | `pytest -m unit -q` | 100% pass |
| 7 | Integration Tests | pytest | `pytest -m integration -q` | 100% pass |
| 8 | Architecture | arch-linter | `python -m scripts.architecture_linter` | Zero ERROR |
| 9 | Dependency Graph | dgv | `python -m scripts.dgv` | Zero cycles, zero forbidden edges |
| 10 | Security | pip-audit, safety, pytest | `pip-audit`, `safety check`, `pytest -m security` | Zero HIGH/CRITICAL |
| 11 | Performance | pytest-benchmark | `pytest -m perf --benchmark-compare` | p95 ≤ budget, no regression > 5% |
| 12 | Coverage | pytest-cov | `pytest --cov=core --cov=api --cov-branch` | ≥ 80% general, 100% security |
| 13 | Documentation | interrogate | `interrogate -vv core/ api/` | ≥ 95% docstring coverage |
| 14 | Decision Traceability | custom | `python -m scripts.trace_check` | All public symbols have TRACE-ID |
| 15 | Governance | custom | `python -m scripts.governance_check` | All required artifacts present |

---

## 4. Configuration Files

- `pyproject.toml` — ruff, mypy, pytest configuration
- `.architecture-linter.toml` — Architecture Linter rules
- `pytest.ini` — markers, paths, async mode
- `requirements.txt` — runtime deps
- `requirements-dev.txt` — dev/test deps (pytest, pytest-benchmark, etc.)
- `.github/workflows/ci.yml` — GitHub Actions pipeline (or equivalent for other CI)
- `scripts/architecture_linter.py` — custom Architecture Linter
- `scripts/dgv.py` — custom Dependency Graph Validator
- `scripts/trace_check.py` — custom TRACE validator
- `scripts/governance_check.py` — custom Governance validator

---

## 5. Pipeline Variants

### 5.1 Pre-commit (local, fast)

Stages: 3, 4, 6 (unit only), 8 (architecture, fast subset)
Time budget: < 30 seconds
Failure: blocks `git commit`

### 5.2 PR (CI, comprehensive)

Stages: all 15
Time budget: < 10 minutes
Failure: blocks merge

### 5.3 Main (post-merge)

Stages: all 15 + smoke tests + build Docker image
Time budget: < 15 minutes
Failure: alerts on-call; revert commit

### 5.4 Release (pre-tag)

Stages: all 15 + Release Readiness Gate (8 items)
Time budget: < 30 minutes
Failure: blocks tag creation

---

## 6. Branch Protection Rules

For `main`:
- Required status checks: all 15 stages + 8 RRG items
- Require review from 1 approver (2 for `core/security/**` and `core/memory/**`)
- No force-push
- No direct commits (PR-only)
- Linear history (squash or rebase merge)

---

## 7. Failure Response

| Stage | Owner | SLA |
|---|---|---|
| 3-7 (lint, format, type, test) | Author of commit | Fix within 1 hour |
| 8-9 (architecture, dep graph) | Architect or Memory Lead | Fix or rollback within 4 hours |
| 10 (security) | Security Agent | Immediate; security veto |
| 11 (performance) | Memory Lead | Fix or relax budget via CR |
| 12 (coverage) | Author | Add tests within 1 day |
| 13 (docs) | Author | Update docs within 1 day |
| 14 (trace) | Author + Lead | Add TRACE-ID within 4 hours |
| 15 (governance) | Lead + Architect | Update governance artifacts within 1 day |

---

## 8. Pre-M6 Pipeline Readiness

M5.5 (Engineering Governance Freeze) must produce:

- [ ] `pyproject.toml` configured (ruff, mypy, pytest, coverage)
- [ ] `pytest.ini` configured (markers: unit, integration, security, perf)
- [ ] `.github/workflows/ci.yml` with all 15 stages
- [ ] `scripts/architecture_linter.py` (basic implementation)
- [ ] `scripts/dgv.py` (basic implementation)
- [ ] `scripts/trace_check.py` (basic implementation)
- [ ] `scripts/governance_check.py` (basic implementation)
- [ ] Branch protection rules applied to `main`
- [ ] All M5.x tests passing in the new pipeline

This is the M5.5 acceptance criteria.

---

## 9. Versioning

- v1.0 (2026-07-03): CI/CD pipeline defined. 15 stages, 4 pipeline variants, M5.5 readiness checklist.
