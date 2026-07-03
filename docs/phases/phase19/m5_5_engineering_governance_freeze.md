# M5.5 — Engineering Governance Freeze

**Status:** PROPOSED (insertion into Phase 19)
**Date:** 2026-07-03
**Owner:** Engineering Governance Lead (architect)
**Authority:** AGENTS.md §5 (Implementation Lifecycle), §8 (CR Process)
**Affects:** [docs/81_PHASE_19_IMPLEMENTATION_PLAN.md](../81_PHASE_19_IMPLEMENTATION_PLAN.md)

---

## 1. Purpose

M5.5 is a **non-code milestone** that sits between M5 (Retention) and M6 (Knowledge Graph). It exists to **officially freeze** all the governance artifacts and tooling that the user has been asking for, so that every future milestone (M6 onward) inherits a verified, executable, enforceable engineering process.

**Rule:** M6.0 code MUST NOT start until M5.5 is FROZEN. This is a hard gate.

---

## 2. Why a Separate Milestone?

The user has observed that JARVIS was operating at ~8.5/10 engineering maturity despite excellent foundations. The gap was *enforcement* — the governance was documented but not yet:

1. **Officially adopted** as the binding process (it was still PROPOSED).
2. **Tooled** so violations are caught automatically.
3. **Verified** that the tooling works on the existing codebase.
4. **Frozen** so future milestones inherit it without re-litigating.

M5.5 produces the **governance freeze** that makes "build first, think later" impossible.

---

## 3. Scope — What M5.5 Freezes

### 3.1 Governance Documents (already drafted, now FROZEN)

| Doc | Path | Status |
|---|---|---|
| Engineering Governance 2.0 entry-point | [docs/governance/pre_milestone_gate.md](../governance/pre_milestone_gate.md) | FROZEN at M5.5 |
| Architecture Review Board (ARB) | [docs/governance/architecture_review_board.md](../governance/architecture_review_board.md) | FROZEN at M5.5 |
| Design Review Gate (DRG) | [docs/governance/design_review_gate.md](../governance/design_review_gate.md) | FROZEN at M5.5 |
| Threat Modeling (STRIDE) | [docs/governance/threat_modeling.md](../governance/threat_modeling.md) | FROZEN at M5.5 |
| Compatibility Matrix | [docs/governance/compatibility_matrix.md](../governance/compatibility_matrix.md) | FROZEN at M5.5 |
| Engineering Decision Log (EDL) | [docs/governance/engineering_decision_log.md](../governance/engineering_decision_log.md) | FROZEN at M5.5 |
| RFC Process | [docs/governance/rfc_process.md](../governance/rfc_process.md) | FROZEN at M5.5 |
| Quality Gates Engine (QGE) | [docs/governance/quality_gates_engine.md](../governance/quality_gates_engine.md) | FROZEN at M5.5 |
| Architecture Linter | [docs/governance/architecture_linter.md](../governance/architecture_linter.md) | FROZEN at M5.5 |
| Dependency Graph Validator (DGV) | [docs/governance/dependency_graph_validator.md](../governance/dependency_graph_validator.md) | FROZEN at M5.5 |
| Decision Traceability | [docs/governance/decision_traceability.md](../governance/decision_traceability.md) | FROZEN at M5.5 |
| Release Readiness Gate (RRG) | [docs/governance/release_readiness_gate.md](../governance/release_readiness_gate.md) | FROZEN at M5.5 |
| CI/CD Pipeline | [docs/governance/ci_cd_pipeline.md](../governance/ci_cd_pipeline.md) | FROZEN at M5.5 |

### 3.2 Tooling (must be implemented and tested at M5.5)

| Tool | Path | Deliverable |
|---|---|---|
| Architecture Linter | `scripts/architecture_linter.py` | Working linter with 30+ rules, all enabled, passes on M5 codebase |
| Dependency Graph Validator | `scripts/dgv.py` | Working graph generator + cycle detector; renders PNG |
| Traceability Checker | `scripts/trace_check.py` | Validates TRACE.md against the code |
| Governance Checker | `scripts/governance_check.py` | Validates required artifacts exist for a given scope |
| CI/CD Pipeline | `.github/workflows/ci.yml` (or equivalent) | 15 stages running on every PR |
| pyproject.toml | `pyproject.toml` | ruff, mypy, pytest, coverage configured |
| pytest.ini | `pytest.ini` | Markers: unit, integration, security, perf |
| Branch protection | GitHub settings | 15 required status checks on `main` |

### 3.3 Backlog Cleanup (must be resolved at M5.5)

- [ ] CR-1907 resolved (A / B / C)
- [ ] Redundant `docs/adr/ADR-001-Knowledge-Graph-Storage.md` merged or archived
- [ ] Naming convention harmonized (kebab-case vs underscore for ADRs)
- [ ] AGENTS.md Phase Status Board updated to include M5.5

---

## 4. M5.5 Sub-Milestones (Plan)

M5.5 is itself broken into 5 sub-milestones, each independently passing the Pre-Milestone Gate and mini quality gate.

| Sub-milestone | Deliverable | Quality Gate |
|---|---|---|
| **M5.5.0** Governance freeze (docs) | All 13 governance docs marked `STATUS: FROZEN` with version + date | Docs review + version check |
| **M5.5.1** Architecture Linter | `scripts/architecture_linter.py` working; all 30+ rules pass on M5 codebase; ≥ 90% test coverage of the linter itself | ruff + mypy + pytest + Architecture Linter passes on itself |
| **M5.5.2** Dependency Graph Validator | `scripts/dgv.py` working; graph rendered; no cycles detected in M5 codebase; ≥ 90% test coverage | ruff + mypy + pytest |
| **M5.5.3** Traceability + Governance Checkers | `scripts/trace_check.py` + `scripts/governance_check.py` working; CI integration tested | ruff + mypy + pytest + dry-run on M5 |
| **M5.5.4** CI/CD Pipeline + Branch Protection | `.github/workflows/ci.yml` with 15 stages; branch protection enabled; full M5 test suite runs green | Pipeline runs end-to-end on M5 codebase |
| **M5.5.5** M5.5 Freeze | All artifacts FROZEN; M5.5 Master Report generated; status updated in AGENTS.md §12 (proposed) | RRG (8 items) all PASS |

---

## 5. Pre-Milestone Gate for M5.5 (each sub-milestone)

Each M5.5.x sub-milestone passes the 12-checkpoint Pre-Milestone Gate. Notable for M5.5:

- **2.1 Spec frozen?** — Each governance doc is treated as a spec for its sub-milestone. FROZEN at the sub-milestone level.
- **2.2 ADR exists?** — ADR-005 (KG) covers the M6 motivation; M5.5 itself is governance, not architecture — no new ADR needed.
- **2.5 Error contract frozen?** — For linter tools, errors are exit codes (0 = pass, 1 = violations, 2 = internal error) and a JSON output schema.
- **2.6 Event contract frozen?** — Linter may emit `governance.linter.violation` events on the EventBus for IDE integration (optional).
- **2.7 Architecture reviewed?** — Architect reviews each linter rule.
- **2.8 Tests designed first?** — Test plan for each linter rule: input (a violating code snippet) → output (expected violation report).
- **2.10 Performance budget?** — Linter must run in < 5 seconds on the full M5 codebase.
- **2.11 Security review?** — Linter itself must be safe: no `eval`, no `exec`, no network calls; input is local code only.
- **2.12 Future compatibility?** — Linter output schema is versioned (v1.0); new rules are additive (MINOR bump).

---

## 6. Quality Gates for M5.5

Each M5.5.x sub-milestone runs the **9 mandatory QGE gates**:

- **G1 Architecture:** The linter itself passes its own rules (dogfooding).
- **G2 Test:** ≥ 90% coverage of the linter code.
- **G3 Coverage:** Tooling code is the new code in this milestone; ≥ 90% required.
- **G4 Security:** STRIDE for the linter (no code execution; only AST parsing).
- **G5 Performance:** Linter < 5s on M5 codebase.
- **G6 Compatibility:** Linter output schema v1.0 frozen.
- **G7 Documentation:** All public functions documented; CLI help text complete.
- **G8 Dependency:** New deps (if any) justified.
- **G9 Governance:** Required artifacts present (this milestone is the artifact).

---

## 7. Release Readiness Gate for M5.5 (the final sub-milestone)

When M5.5.5 freezes, the RRG runs:

| # | Item | Evidence |
|---|---|---|
| 1 | Architecture | Linter + DGV pass on M5 codebase; M5 itself passes the rules |
| 2 | Security | STRIDE for the linter tools |
| 3 | Coverage ≥ 96% | Tooling code is small but well-tested |
| 4 | Performance | Linter < 5s; DGV < 10s on M5 codebase |
| 5 | Observability | Optional event emission from linter |
| 6 | Compatibility | Linter output schema v1.0 frozen |
| 7 | Rollback | M5.5 changes are additive (new tools, new docs); rollback = remove tools + revert docs |
| 8 | Documentation | All 13 governance docs FROZEN with date; CHANGELOG updated |

---

## 8. Effect on M6

After M5.5 freezes:

- **M6.0 DTOs** must use the Architecture Linter to validate layer direction.
- **M6.1 Validator** must be written with test-first discipline (Pre-Milestone Gate item 2.8).
- **M6.2 Repository** must pass DGV (no cycles introduced).
- **M6.x** must update TRACE.md for every new public symbol.
- **M6.9 Freeze** must pass the RRG (8 items).
- **M7, M8, M9, M10, M11** all inherit the same process.

**M5.5 is the inflection point:** after it, JARVIS is no longer "a project that happens to have governance" — it is "a project whose governance is enforced by tooling on every commit."

---

## 9. Acceptance Criteria

M5.5 is FROZEN when:

- [ ] All 13 governance documents have `STATUS: FROZEN`, version, and date in their headers
- [ ] `scripts/architecture_linter.py` exists, passes on M5 codebase, ≥ 90% tested
- [ ] `scripts/dgv.py` exists, renders graph, no cycles, ≥ 90% tested
- [ ] `scripts/trace_check.py` exists, validates TRACE.md
- [ ] `scripts/governance_check.py` exists, validates required artifacts
- [ ] `.github/workflows/ci.yml` runs all 15 stages green on M5 codebase
- [ ] Branch protection enabled on `main` with 15 required checks
- [ ] CR-1907 resolved
- [ ] Redundant ADR-001-KG-Storage resolved (merged or archived)
- [ ] Naming convention harmonized
- [ ] M5.5 Master Report filed at `docs/reports/m5_5_freeze_report.md`
- [ ] AGENTS.md §12 Phase Status Board updated (proposed change) to add M5.5 line

---

## 10. Sign-off

```markdown
## M5.5 — Engineering Governance Freeze Sign-off

I have reviewed the M5.5 deliverables and authorize M6.0 (Knowledge Graph) to begin.

| Role | Name | Date |
|---|---|---|
| Architect | | |
| Engineering Governance Lead | | |
| Security Agent | | |
| Memory Lead (incoming M6 owner) | | |

Until this block is signed, M6.0 is BLOCKED.
```

---

## 11. Time and Effort Estimate

M5.5 is **not** a tiny milestone. It is a meta-milestone that creates the tooling for all future milestones. Estimate (intentionally vague per the system prompt — no promises):

- M5.5.0 (docs freeze): small — 1-2 hours
- M5.5.1 (Architecture Linter): medium — significant code
- M5.5.2 (DGV): medium — significant code
- M5.5.3 (Trace + Governance): small — code that wraps existing logic
- M5.5.4 (CI/CD): small — yaml + integration
- M5.5.5 (Freeze): small — documentation + sign-off

The investment is amortized across all future milestones. After M5.5, the cost of *any* milestone decreases because the governance is automated.

---

## 12. Versioning

- v1.0 (2026-07-03): M5.5 milestone proposed. Inserts between M5 and M6 in Phase 19 plan.
