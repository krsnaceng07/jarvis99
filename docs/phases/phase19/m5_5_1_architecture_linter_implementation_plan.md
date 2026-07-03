# M5.5.1 — Architecture Linter Implementation Plan

**STATUS:** APPROVED
**VERSION:** 2.0
**DATE:** 2026-07-03
**SUPERSEDES:** v1.0 (2026-07-03) — v1.0 conflicts with frozen specs in §6 (exit codes 3/4) and §2 (file location `tools/`) resolved by spec-first rule
**APPROVED BY:** Architect (user)
**AUTHORITY:** AGENTS.md §1, §5, §6.1; M5.5 freeze doc §4; architecture_linter.md v1.0 (FROZEN at M5.5.0)
**Affects:** `scripts/architecture_linter.py`, `.architecture-linter.toml`, `tests/test_architecture_linter.py`, `tests/fixtures/linter/`

---

## 1. Objective

Implement the Architecture Linter per [frozen spec v1.0](../../governance/architecture_linter.md), with 6 active rule categories, CLI, JSON v1.0 output, ≥ 90% overall test coverage, **100% coverage on the core engine** (Rule Engine, Registry, Runner), and a dogfooding pass on the M5 codebase.

**The linter is responsible ONLY for architecture rules.** It does NOT enforce ADR references, documentation, contracts, traceability, or test presence — those belong to the Governance Checker (M5.5.3).

---

## 2. Implementation Constraints (binding)

These constraints derive from the architect's directive (2026-07-03) and AGENTS.md §6.1. They are non-negotiable for M5.5.1:

### 2.1 Frozen Specification Precedence
If the Implementation Plan conflicts with any frozen specification, the frozen specification always takes precedence. The Plan may clarify implementation details but must not redefine normative requirements (rule IDs, rule semantics, exit codes, file paths, severity defaults, output schema).

### 2.2 No Scope Expansion
M5.5.1 is limited to the Architecture Linter. Governance checks (ADR validation, contract enforcement, traceability, test presence, release readiness, etc.) remain in **M5.5.3 Governance Checker**. The linter MUST NOT absorb these concerns, even if they look architecturally related.

### 2.3 No Unapproved Rule Changes
The rule set is frozen (LR/NBR/NSD/NDE/NUC/NCP, plus KG-1..7 stubs). Any change to rule IDs, semantics, severity, or detection logic requires:
1. RFC (per [docs/governance/rfc_process.md](../../governance/rfc_process.md))
2. ADR (per [docs/architecture/adrs/](../../architecture/adrs/))
3. Architecture Review Board approval (per [docs/governance/architecture_review_board.md](../../governance/architecture_review_board.md))
4. Version bump of the linter spec
5. Governance freeze update

### 2.4 Review Discipline
Follow one sub-milestone at a time (A → Review → Approval → B → Review → Approval → C ...). No subsequent sub-milestone begins until the current one is approved by the architect. One sub-milestone = one report = one review.

---

## 3. Scope

| IN | OUT |
|---|---|
| `scripts/architecture_linter.py` (per spec §2) | DGV — M5.5.2 |
| `scripts/__init__.py` | Governance Check — M5.5.3 |
| `.architecture-linter.toml` | CI/CD pipeline — M5.5.4 |
| `tests/test_architecture_linter.py` | Any new rules beyond spec v1.0 |
| `tests/fixtures/linter/` (sample code) | Modifications to existing `core/`/`api/` code (unless dogfooding in F reveals real violations) |
| KG-1..7 rule stubs (disabled) | AGENTS.md §12 update (deferred to M5.5.5) |

---

## 4. Architecture

Single file at `scripts/architecture_linter.py` per frozen spec §2. Class decomposition INSIDE the file:

```
scripts/architecture_linter.py
├── ArchitectureLinter          # engine / orchestrator
├── Rule (ABC)                  # rule base
├── RuleRegistry                # registry
├── LinterConfig.from_toml      # config loader
├── FileContext (frozen)        # per-file rule input
├── Violation (frozen)          # rule violation record
├── Severity (StrEnum)          # error | warn | info
├── Reporter (ABC)
│   ├── TextReporter            # human output, deterministic
│   └── JsonReporter            # JSON v1.0 schema
├── Report (frozen)             # output aggregate
├── ExitCodeManager             # 0 | 1 | 2 (per spec §6)
└── main(argv) -> int           # CLI entry

# (Future) If rule code volume justifies it in B–F, a sub-package
# `scripts/architecture_linter/rules/{lr,nbr,nsd,nde,nuc,ncp,kg}/`
# may be introduced WITHOUT violating spec §2 (the package lives under
# `scripts/`; `scripts/architecture_linter.py` becomes a thin re-export
# shim, OR is removed in favor of `scripts/architecture_linter/__init__.py`).
#
# **Any structural change from `scripts/architecture_linter.py` to a package
# requires an approved CR and must not occur during M5.5.1 unless explicitly
# authorized.** (Per architect directive 2026-07-03, refining "Decision
# deferred to B".)
```

The "core engine" for 100% coverage is defined as: `ArchitectureLinter`, `RuleRegistry`, and the dispatch/run logic in `ArchitectureLinter.lint()` / `_lint_file()`. These three are the linter's load-bearing components and warrant maximum test scrutiny.

---

## 5. Rule Inventory (frozen spec → implementation)

| Rule | Severity | Detection |
|---|---|---|
| **LR-1** core/ must not import api/, cli/, ui/ | ERROR | AST import scan by file path prefix |
| **LR-2** api/ must not import private core files | ERROR | AST import scan (`_private`/`_internal` segments) |
| **LR-3** ui/ must not import core/ directly | ERROR | AST import scan |
| **LR-4** cli/ must not import from api/ or ui/ | ERROR | AST import scan |
| **LR-5** Layer direction UI→API→Brain→Memory+Tools | ERROR | AST + path analysis |
| **NBR-1** *Repository: no process/decide/validate/score/rank/recommend methods | ERROR | AST method-name regex |
| **NBR-2** *Repository: no LLM/embedding calls | ERROR | AST call scan, forbidden name list |
| **NBR-3** *Repository: no direct bus.publish | ERROR | AST call scan |
| **NBR-4** *Repository: no graph merge | ERROR | AST call scan |
| **NSD-1** *Engine: no DB writes | ERROR | AST call scan (`db.execute`, `session.add`, etc.) |
| **NSD-2** *Engine: no input mutation | WARN | AST assign scan on input args |
| **NSD-3** *Engine: no tool/external calls | ERROR | AST call scan |
| **NDE-1** DTO files: no Repository/Engine/Service imports | ERROR | AST import scan in `*dto.py`/`*types.py` |
| **NDE-2** DTOs must be BaseModel | ERROR | AST class scan, base class check |
| **NDE-3** DTOs must have schema_version | ERROR | AST attr scan |
| **NUC-1** core/: no fastapi/starlette/flask/click/typer/rich/textual | ERROR | AST import scan |
| **NUC-2** core/: no tkinter/pyqt/kivy/playwright | ERROR | AST import scan |
| **NCP-1** Frozen phase: no import from non-frozen | ERROR | AST + freeze registry lookup |
| **NCP-2** Forward references blocked | (mypy) | not linter's job; linter emits info hint |
| **KG-1..7** M6-specific | ERROR | stubbed, disabled in config until M6 |

**Total: 18 active ERROR rules + 1 WARN + 1 NCP-2 info hint + 7 KG stubs.**

---

## 6. Configuration Format (`.architecture-linter.toml`)

```toml
[general]
severity_default = "error"
exclude = ["tests/", "archive/", "scripts/"]
output_format = "text"
fail_on = "error"

[rules.LR]
enabled = true
severity = "error"

[rules.NBR]
enabled = true
severity = "error"

[rules.NSD]
enabled = true
severity = "error"

[rules.NDE]
enabled = true
severity = "error"

[rules.NUC]
enabled = true
severity = "error"

[rules.NCP]
enabled = true
severity = "error"

[rules.KG]
enabled = false   # enabled in M6
```

---

## 7. CLI Contract (Exit Codes)

Per frozen spec §6 (NON-NEGOTIABLE per §2.1):

| Exit | Meaning |
|---|---|
| 0 | No violations (or only INFO) |
| 1 | Violations of `--fail-on` severity found |
| 2 | Internal error: config missing/invalid, parse error, unhandled exception, **OR** "Configuration Error" / "Invalid Rule Definition" (both surface as code 2 with a descriptive stderr message) |

The v1.0.0 plan proposal added codes 3 (Configuration Error) and 4 (Invalid Rule Definition). Per the architect's decision on 2026-07-03, these are collapsed into code 2 with descriptive messages, in alignment with the frozen spec. This preserves CI integration: scripts that check `exit != 0 && exit != 1` continue to work.

```
python -m scripts.architecture_linter --config .architecture-linter.toml [--path .] [--format text|json] [--fail-on warn|error]
```

---

## 8. JSON Output Schema v1.0

```json
{
  "schema_version": "1.0",
  "tool": "architecture_linter",
  "files_scanned": 42,
  "duration_ms": 1234,
  "violations": [
    {
      "rule_id": "LR-1",
      "severity": "error",
      "file": "core/memory/kg_service.py",
      "line": 12,
      "col": 1,
      "message": "core/ must not import from api/ (forbidden layer dependency)",
      "snippet": "from api.routes import foo"
    }
  ],
  "summary": {"error": 1, "warn": 0, "info": 0}
}
```

---

## 9. Implementation Sub-Milestones (v2.0 ordering)

| Sub | Deliverable | Mini Gate | Status |
|---|---|---|---|
| **M5.5.1.A** Skeleton | `scripts/__init__.py`, `scripts/architecture_linter.py` with all contract types + reporters + CLI. 25 sanity tests. | ruff + mypy + 25 tests pass | ✅ **DONE 2026-07-03** ([A report](../../../PHASE19_M5_5_1_A_REPORT.md)); awaiting architect approval |
| **M5.5.1.B** LR Rules | All LR rules (LR-1..5) + 20 tests (4/rule: positive, 2 negative, regression) | ruff + mypy + 20 tests pass | pending A approval |
| **M5.5.1.C** NBR Rules | All NBR rules (NBR-1..4) + 16 tests + regression suite | ruff + mypy + 16 tests pass; no forbidden business logic in `*Repository` | pending B approval |
| **M5.5.1.D** NSD Rules | All NSD rules (NSD-1..3) + 12 tests + cycle-detection support hooks | ruff + mypy + 12 tests pass; no side-effects in `*Engine` | pending C approval |
| **M5.5.1.E** NDE + NUC Rules | All NDE rules (NDE-1..3) + All NUC rules (NUC-1..2) + 20 tests | ruff + mypy + 20 tests pass; dependency direction validated | pending D approval |
| **M5.5.1.F** NCP Rules + CI + Reporter + Freeze | NCP rules (NCP-1..2) + KG-1..7 stubs (disabled) + CI integration hook (`.github/workflows/ci.yml` extension) + Reporter hardening (golden-file tests) + final freeze report `PHASE19_M5_5_1_REPORT.md` + dogfooding pass on M5 codebase | ruff + mypy + ALL tests pass; ≥ 90% overall coverage; **100% on core engine**; linter self-dogfoods (passes on its own code); pipeline blocks on violations | pending E approval |

**Per-sub-milestone review discipline (§2.4):** Each sub-milestone produces one report. No B begins until A is approved. No C begins until B is approved. Etc.

---

## 10. Test Plan

| Test type | Count | Notes |
|---|---|---|
| Per-rule positive | 18 (1/rule) | no violation expected |
| Per-rule negative | 36 (2/rule) | distinct violation samples |
| Per-rule regression | 18 (1/rule) | frozen spec example verbatim |
| Golden-file (reporter) | 6 | text+json × 3 sample sizes |
| Sanity (skeleton, in A) | 25 | contract types, reporters, exit codes, CLI |
| **Total** | **≥ 103** | |

### Coverage Targets

| Scope | Target | Source |
|---|---|---|
| Overall linter code | ≥ 90% | M5.5 freeze doc §6 (G3) |
| **Core engine** (`ArchitectureLinter`, `RuleRegistry`, dispatch in `lint()`/`_lint_file()`) | **100%** | Architect directive, 2026-07-03 |
| Other modules (`Reporters`, `ExitCodeManager`, `LinterConfig`, `Violation`, etc.) | ≥ 90% | M5.5 freeze doc §6 |

**100% coverage applies to all reachable executable paths in the defined core engine. Unreachable defensive branches may be excluded only with documented justification in the coverage report.** This applies to `ArchitectureLinter`, `RuleRegistry`, and the dispatch in `lint()` / `_lint_file()`. The 100% target aligns with the spirit of the frozen governance (100% on `core/security/**` per QGE §3.3) and gives maximum confidence in the linter's load-bearing path.

---

## 11. Performance Budget (verification in M5.5.1.F)

| Metric | Target |
|---|---|
| Lint full M5 codebase | < 5s |
| Test suite | < 30s |
| Memory peak | < 200MB |
| Single-file lint | < 50ms (median) |

---

## 12. Quality Gate (per sub-milestone)

- `ruff format --check scripts tests` → clean
- `ruff check scripts/architecture_linter.py scripts/__init__.py tests/test_architecture_linter.py` → 0 errors
- `mypy --strict scripts/architecture_linter.py` → 0 errors
- `pytest tests/test_architecture_linter.py [--cov-branch] [--cov-fail-under=90]` → all pass, coverage targets met
- (F only) `python -m scripts.architecture_linter --config .architecture-linter.toml scripts/` → 0 violations (self-dogfooding)
- (F only) `python -m scripts.architecture_linter --config .architecture-linter.toml` (whole repo) → 0 violations OR all violations justified

Pre-existing errors in `tests/test_memory_retrieval_engine.py` (E402, F821×2) are M5-baseline issues, out of M5.5.1.A scope. They will be addressed in F dogfooding pass.

---

## 13. Risk Register

| ID | Risk | Mitigation |
|---|---|---|
| R1 | AST parsing misses dynamic imports (`importlib`, `__import__`) | NCP-2 hint + mypy coverage; linter does not block |
| R2 | False positives in M5 codebase | All violations reviewed; fixed, OR permanently suppressed. **Any permanent suppression must include: (1) Rule ID, (2) Reason, (3) ADR/CR reference if applicable, (4) Review owner, (5) Expiry or review date if temporary.** |
| R3 | mypy `core.*` override hides linter type errors | Linter lives in `scripts/`, override does not apply; verified by mypy run |
| R4 | Performance regression as codebase grows | M5.5.4 CI integration adds caching; out of M5.5.1 scope |
| R5 | Windows path separator mismatch (covered in A) | `_collect_files` uses `Path.as_posix()`; tested in `test_lint_collect_files_respects_exclude` |

---

## 14. Acceptance Criteria (DoD)

- [ ] All 6 active rule categories implemented per frozen spec
- [ ] KG-1..7 stubs present (disabled by default)
- [ ] JSON output schema v1.0 frozen and tested
- [ ] Exit codes 0/1/2 implemented (per spec §6; codes 3/4 from v1.0.0 proposal collapsed to 2)
- [ ] `.architecture-linter.toml` parser works
- [ ] CLI help text complete (`--help` works)
- [ ] ≥ 90% overall test coverage on linter code
- [ ] **100% coverage on core engine** (per architect directive)
- [ ] Linter passes on itself (self-dogfooding)
- [ ] Linter passes on M5 codebase (zero violations OR all justified)
- [ ] `PHASE19_M5_5_1_REPORT.md` (full milestone) generated
- [ ] AGENTS.md §12 NOT updated (deferred to M5.5.5 per §2.2)
- [ ] No frozen interface modified
- [ ] No scope expansion into governance (M5.5.3) territory

---

## 15. Approval

```
M5.5.1 Implementation Plan Sign-off (v2.0)

I have reviewed the v2.0 plan (reconciled to frozen specs) and authorize
B–F to begin after M5.5.1.A is approved.

| Role | Name | Date |
|---|---|---|
| Architect | (user) | 2026-07-03 |
| Engineering Governance Lead | (user) | 2026-07-03 |

Status: APPROVED 2026-07-03.
v1.0 superseded.
M5.5.1.A implementation complete; awaiting architect approval of A report
before beginning M5.5.1.B (LR rules).
```

---

## 16. Versioning

- **v2.0** (2026-07-03): User revision. Two spec conflicts resolved: (1) exit codes 0/1/2 only (3/4 from v1.0.0 proposal collapsed to 2); (2) file location stays at `scripts/architecture_linter.py` per spec §2 (not `tools/architecture_linter/`). Sub-milestone ordering updated to B=LR, C=NBR, D=NSD, E=NDE+NUC, F=NCP+CI+reporter+freeze. 100% core engine coverage added (§10). Implementation Constraints section added (§2, binding per architect directive). M5.5.1.A marked as ✅ DONE with pointer to A report.
- v1.0 (2026-07-03): Initial plan. Status: **SUPERSEDED** by v2.0.
