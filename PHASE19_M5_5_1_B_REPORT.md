# MILESTONE M5.5.1.B REPORT — Architecture Linter LR Rules

**Completed:** 2026-07-03
**Phase:** 19 / M5.5 (Engineering Governance)
**Sub-milestone:** M5.5.1.B — LayerDirection rules (LR-1..5)
**Plan:** [docs/phases/phase19/m5_5_1_architecture_linter_implementation_plan.md](file:///e:/jarvis/docs/phases/phase19/m5_5_1_architecture_linter_implementation_plan.md) v2.0 (APPROVED)
**Depends on:** M5.5.1.A (APPROVED 2026-07-03)

---

## Completed

Five LayerDirection rules (LR-1..5) implemented per frozen spec [`docs/governance/architecture_linter.md` §3 v1.0](../governance/architecture_linter.md), with 3 helper functions and 23 new tests. The linter now statically enforces the canonical layer direction `UI → API → Brain → Memory + Tools` and the named prohibited dependencies (core→api/cli/ui, api→core._, ui→core, cli→api/ui). The linter self-scans clean (0 violations) because `scripts/` contains no `core/` / `api/` / `ui/` / `cli/` packages.

---

## Files Modified

| File | Responsibility | Δ LOC |
|------|---------------|-------|
| `scripts/architecture_linter.py` | Added 3 helpers (`_file_layer`, `_module_layer`, `_iter_imports`) + 5 LR rule classes (LR1Rule–LR5Rule) + registered them in `build_registry()` | +145 |
| `tests/test_architecture_linter.py` | Added 20 LR tests (4/rule: positive, 2 negative, regression) + 3 helper unit tests; added LR1Rule–LR5Rule to import block | +205 |

No new files created. No config, no fixtures, no docs modified.

---

## Public Interface Changes

| Symbol | Change | Notes |
|--------|--------|-------|
| `_file_layer(path: Path) -> str \| None` | NEW (private) | Top-level layer lookup, e.g. `core/memory/x.py` → `"core"`, `tests/test_x.py` → `None` |
| `_module_layer(module: str \| None) -> str \| None` | NEW (private) | Module → top-level layer, e.g. `"core.memory.x"` → `"core"`, `"fastapi"` → `None` |
| `_iter_imports(tree) -> Iterator[tuple[ast.stmt, str]]` | NEW (private) | Yields `(node, module)` for every static, non-relative import |
| `LR1Rule` | NEW | `core/` must not import from `api/`/`cli/`/`ui/` (Severity.ERROR) |
| `LR2Rule` | NEW | `api/` must not import private `core/` files (names with leading `_`) (Severity.ERROR) |
| `LR3Rule` | NEW | `ui/` must not import `core/` directly (Severity.ERROR) |
| `LR4Rule` | NEW | `cli/` must not import from `api/` or `ui/` (Severity.ERROR) |
| `LR5Rule` | NEW | Generic layer direction check: `UI(0)→API/CLI(1)→Brain/Core(2)→Memory/Tools(3)`; upstream imports are violations (Severity.ERROR) |
| `build_registry()` | EXTENDED | Now registers `LR1Rule`–`LR5Rule` (was: empty) |

**No change** to public reporter / config / exit-code / CLI surface. The `Rule` ABC and registry are reused as-is from A.

---

## Frozen Rule Semantics (B subset)

Verbatim from [architecture_linter.md v1.0 §3](../governance/architecture_linter.md):

| Rule | Source | Detection (implemented) |
|------|--------|-------------------------|
| **LR-1** | spec §3.1 | If `_file_layer(ctx.path) == "core"` AND `_module_layer(import) in {"api", "cli", "ui"}` → violation |
| **LR-2** | spec §3.2 | If `_file_layer(ctx.path) == "api"` AND `_module_layer(import) == "core"` AND any non-first module segment starts with `_` → violation |
| **LR-3** | spec §3.3 | If `_file_layer(ctx.path) == "ui"` AND `_module_layer(import) == "core"` → violation |
| **LR-4** | spec §3.4 | If `_file_layer(ctx.path) == "cli"` AND `_module_layer(import) in {"api", "ui"}` → violation |
| **LR-5** | spec §3.5 | Layer rank `{ui:0, api:1, cli:1, brain:2, core:2, memory:3, tools:3}`; if `from_rank > to_rank` → violation |

All five rules are static (AST-only), have no I/O side effects, and yield zero or more `Violation` per file.

---

## Tests Added (23)

| Test | Asserts |
|------|---------|
| `test_lr1_positive_core_imports_brain` | `core/` importing `brain/` → 0 violations |
| `test_lr1_negative_core_imports_api` | `core/` importing `api.foo` → 1× LR-1 |
| `test_lr1_negative_core_imports_ui` | `core/` importing `ui.bar` → 1× LR-1 |
| `test_lr1_regression_spec_example` | Spec §3.1 example verbatim → 1× LR-1 |
| `test_lr2_positive_api_imports_public_core` | `api/` importing `core.foo` (public) → 0 violations |
| `test_lr2_negative_api_imports_underscore_top` | `api/` importing `core._internal` → 1× LR-2 |
| `test_lr2_negative_api_imports_underscore_nested` | `api/` importing `core.foo._bar` → 1× LR-2 |
| `test_lr2_regression_spec_example` | Spec §3.2 example verbatim → 1× LR-2 |
| `test_lr3_positive_ui_imports_api` | `ui/` importing `api/` (allowed) → 0 violations |
| `test_lr3_negative_ui_imports_core_top` | `ui/` importing `core` (top-level) → 1× LR-3 |
| `test_lr3_negative_ui_imports_core_submodule` | `ui/` importing `core.foo` → 1× LR-3 |
| `test_lr3_regression_spec_example` | Spec §3.3 example verbatim → 1× LR-3 |
| `test_lr4_positive_cli_imports_core` | `cli/` importing `core/` (allowed) → 0 violations |
| `test_lr4_negative_cli_imports_api` | `cli/` importing `api/` → 1× LR-4 |
| `test_lr4_negative_cli_imports_ui` | `cli/` importing `ui/` → 1× LR-4 |
| `test_lr4_regression_spec_example` | Spec §3.4 example verbatim → 1× LR-4 |
| `test_lr5_positive_layer_respects_direction` | `api/` importing `core/` (downstream) → 0 violations |
| `test_lr5_negative_brain_imports_api` | `brain/` importing `api/` (upstream) → 1× LR-5 |
| `test_lr5_negative_core_imports_ui` | `core/` importing `ui/` (upstream) → 1× LR-5 |
| `test_lr5_regression_spec_example` | Spec §3.5 example verbatim → 1× LR-5 |
| `test_file_layer_returns_none_for_unrecognized_path` | `_file_layer("tests/test_x.py")` → `None` |
| `test_module_layer_returns_none_for_external` | `_module_layer("fastapi")` → `None` |
| `test_iter_imports_skips_relative` | `from . import x` / `from ..pkg import y` → not yielded |

Test pattern: each rule has 1 positive (no violation), 2 negative (distinct violation samples), 1 regression (spec example verbatim). Helper tests cover the 3 documented "return None" defensive branches.

---

## Quality Gate (M5.5.1.B mini gate)

| Check | Command | Result |
|-------|---------|--------|
| Format | `ruff format --check scripts/architecture_linter.py scripts/__init__.py tests/test_architecture_linter.py` | ✅ 3 files already formatted |
| Lint (affected files) | `ruff check scripts/architecture_linter.py scripts/__init__.py tests/test_architecture_linter.py` | ✅ All checks passed! |
| Types | `mypy --strict scripts/architecture_linter.py` | ✅ Success: no issues found in 1 source file |
| Tests | `pytest tests/test_architecture_linter.py -v` | ✅ 48/48 passed in 4.26s |
| Coverage (overall) | `pytest --cov=scripts.architecture_linter --cov-branch --cov-fail-under=90` | ✅ 90.29% (target ≥ 90%) |
| Self-dogfooding (B scope) | `python -m scripts.architecture_linter --config .architecture-linter.toml --path scripts` | ✅ 2 files scanned, 0 violations (scripts/ has no recognizable layer) |
| CLI smoke (regression) | `--help` exits 0; missing config → exit 2; clean run → exit 0 | ✅ |

> **Note on coverage:** The plan's 100% core-engine target is reserved for **M5.5.1.F**, not B. B's gate (per plan §12) is "ruff + mypy + 20 tests pass" — all met. The 23 B-tests (20 LR + 3 helpers) and 25 A-tests (48 total) pass at 90.29% overall coverage. The 100% core-engine check is part of the F acceptance criteria and will be re-measured after C/D/E add their rule categories.

---

## Pre-existing Issues Noted (out of M5.5.1.B scope)

`ruff check tests/` still reports 3 pre-existing errors in `tests/test_memory_retrieval_engine.py` (E402, F821×2) from M4. These are unchanged from the A report and remain slated for the F dogfooding pass.

---

## Risk Register Update

| ID | Status | Notes |
|----|--------|-------|
| R1 (AST misses dynamic imports) | unchanged | NCP-2 hint + mypy coverage |
| R2 (False positives in M5) | tracked | Will surface in F dogfooding |
| R3 (mypy core.* override) | mitigated | Linter lives in `scripts/`, override does not apply; verified by mypy run |
| R4 (Performance regression) | tracked | F verification |
| R5 (Windows path separator) | mitigated (A) | `_collect_files` uses `Path.as_posix()`; tested in A |
| **R6 (NEW)** LR rules double-reporting with LR-5 | mitigated | LR-1..4 are *named* prohibitions; LR-5 is the *generic* backstop. A forbidden import can trigger BOTH the named rule and LR-5. The reporter's deduplication key is the 4-tuple `(file_path, line, column, rule_id)` — violations are deduplicated per (file, line, col, rule), not just per (file, line, col). This means a single forbidden import may emit 2 distinct violations (one for the named rule, one for LR-5), each reported separately. Reporters should NOT silently collapse across rule_ids. Documented in coverage report. |
| **R7 (NEW)** Mypy strict required `ast.stmt` not `ast.AST` | mitigated | `_iter_imports` return type changed to `Iterator[tuple[ast.stmt, str]]`. Rationale documented inline. |

---

## Acceptance Criteria (from plan §13) — M5.5.1.B subset

- [x] All 5 LR rule classes implemented per frozen spec §3
- [x] All 5 rules registered in `build_registry()`
- [x] 20 LR tests (4/rule: positive, 2 negative, regression) — delivered
- [x] 3 helper unit tests for 100% core-engine helper coverage — delivered
- [x] No new public interfaces beyond what's documented
- [x] No frozen interface modified
- [x] ruff clean (affected files)
- [x] mypy strict clean
- [x] ≥ 90% overall test coverage on linter code — **90.29%** (target met)
- [ ] 100% core engine coverage — **deferred to M5.5.1.F** (per plan §10)
- [ ] Linter passes on M5 codebase (dogfooding) — **deferred to M5.5.1.F**
- [ ] All 6 active rule categories implemented — **deferred to M5.5.1.C–E**

---

## Known Limitations

The Architecture Linter (LR rules subset) intentionally does not resolve the following import patterns. These are out of LR rule scope and are deferred to **M5.5.3 Governance Checker** (static governance) and runtime checks:

- **Dynamic imports** — `importlib.import_module("foo")`, `__import__("foo")`
- **Runtime monkey patching** — `module.attr = ...` applied at import time
- **Generated Python files** — files in `build/`, `dist/`, `__pycache__/`, or under generated/ directories
- **String-evaluated imports** — `eval("import foo")`, `exec("import foo")`
- **Conditional / programmatic imports** inside `if`/`try` blocks where the module name is not a string literal at parse time

These limitations are by design: LR rules are *static* AST-only checks. They MUST NOT be extended to perform runtime introspection, network calls, or file I/O beyond reading the source file being analyzed.

---

## Gate Status: ✅ PASS

All M5.5.1.B deliverables in place. Frozen spec compliance verified. mypy strict + ruff + 48/48 tests + 90.29% overall coverage. Self-dogfooding clean.

---

## Next: M5.5.1.C — Repository/Business-Logic rules (NBR-1..4)

Per plan §8: implement 4 NBR rules + 16 tests (4/rule: positive, 2 negative, regression). NBR rules enforce the spec's invariant that `*Repository` classes MUST contain only CRUD + transactions + versioning + checksums; no validation, no planning, no business logic, no tool execution. Mini gate: ruff + mypy + 16 tests pass; no forbidden business logic in any `*Repository`.

---

## Architect Sign-off

```
M5.5.1.B Implementation Sign-off

I have reviewed the M5.5.1.B LayerDirection rules (5 rule classes, 23 new
tests, total 48/48 passing, ruff + mypy strict + 90.29% coverage,
self-dogfooding clean) and authorize M5.5.1.C to begin.

| Role | Name | Date |
|---|---|---|
| Architect | (user) | 2026-07-03 |
| Engineering Governance Lead | (user) | 2026-07-03 |

Per §2.4 review discipline of the v2.0 plan, M5.5.1.C (NBR-1..4 rules)
may begin.
```

**Status: ✅ APPROVED 2026-07-03.**

**Conditions (non-blocking):**
1. ✅ Known Limitations section added (above).
2. ✅ Dedup key documented as `(file_path, line, column, rule_id)` (R6).

**Next authorized milestone:** M5.5.1.C — NBR Rules (NBR-1..4) + 16 tests.
