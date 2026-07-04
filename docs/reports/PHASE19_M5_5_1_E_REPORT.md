# MILESTONE M5.5.1.E REPORT — Architecture Linter NDE + NUC Rules

**Completed:** 2026-07-04
**Phase:** 19 / M5.5 (Engineering Governance)
**Sub-milestone:** M5.5.1.E — No-DTO-Misuse + No-UI-in-Core rules (NDE-1..3 + NUC-1..2)
**Plan:** [docs/phases/phase19/m5_5_1_architecture_linter_implementation_plan.md](file:///e:/jarvis/docs/phases/phase19/m5_5_1_architecture_linter_implementation_plan.md) v2.0 (APPROVED)
**Spec:** [docs/governance/architecture_linter.md](file:///e:/jarvis/docs/governance/architecture_linter.md) §3.4 + §3.5 (FROZEN)
**Depends on:** M5.5.1.A (APPROVED), M5.5.1.B (APPROVED), M5.5.1.C (APPROVED), M5.5.1.D (APPROVED)

---

## 1. Summary

Implemented NDE-1, NDE-2, NDE-3, NUC-1, NUC-2 per the frozen specification §3.4 + §3.5. All quality gates pass with 113 total tests (80 before, +33 new for E). The linter correctly implements case-insensitive checks for forbidden imports and properly identifies DTO files by naming convention (*dto.py, *types.py). No frozen interface modified.

---

## 2. Files Modified

| File | Change | LOC delta |
|---|---|---|
| [scripts/architecture_linter.py](file:///e:/jarvis/scripts/architecture_linter.py) | Added NDE helpers (2) + NDE-1/2/3 + NUC-1/2 rule classes | +270 |
| [scripts/architecture_linter.py](file:///e:/jarvis/scripts/architecture_linter.py) | Updated `build_registry()` to include NDE/NUC rules | +10 |
| [tests/test_architecture_linter.py](file:///e:/jarvis/tests/test_architecture_linter.py) | Added 33 NDE/NUC tests + imports | +450 |
| [PHASE19_M5_5_1_E_REPORT.md](file:///e:/jarvis/PHASE19_M5_5_1_E_REPORT.md) | This file (new) | new |

---

## 3. Rule Implementation Summary

### 3.1 NDE-1 — DTO Files Must Not Import Repository/Engine/Service

**Spec reference:** `architecture_linter.md` §3.4 NDE-1

**Detection logic:**
- For every file named *dto.py or *types.py
- Scan `ast.Import` and `ast.ImportFrom` nodes
- Case-insensitive check for forbidden keywords: repository, engine, service in module name or imported aliases
- Emit ERROR

### 3.2 NDE-2 — DTOs Must Be Pydantic BaseModel

**Spec reference:** `architecture_linter.md` §3.4 NDE-2

**Detection logic:**
- For every class in DTO files
- Checks for @dataclass decorator (forbidden)
- Checks for BaseModel in base classes (required)
- Emit ERROR if neither

### 3.3 NDE-3 — DTOs Must Have schema_version Field

**Spec reference:** `architecture_linter.md` §3.4 NDE-3

**Detection logic:**
- For every class in DTO files
- Scans class body for `AnnAssign` or `Assign` to `schema_version`
- Emit ERROR if missing

### 3.4 NUC-1 — core/ Must Not Import UI/web/CLI Frameworks

**Spec reference:** `architecture_linter.md` §3.5 NUC-1

**Detection logic:**
- For every file in core/ directory
- Scan imports for forbidden keywords: fastapi, starlette, flask, click, typer, rich, textual
- Case-insensitive check
- Emit ERROR

### 3.5 NUC-2 — core/ Must Not Import GUI/browser Libraries

**Spec reference:** `architecture_linter.md` §3.5 NUC-2

**Detection logic:**
- For every file in core/ directory
- Scan imports for forbidden keywords: tkinter, pyqt, kivy, playwright
- Case-insensitive check
- Emit ERROR

---

## 4. Test Matrix (33 tests total for E)

### NDE Rules (20 tests)
| # | Test | Pattern | Expected |
|---|---|---|---|
| NDE-1 | `test_nde1_positive_clean_dto_file` | UserDTO with safe imports only | 0 violations |
| NDE-1 | `test_nde1_positive_non_dto_file_ignored` | Service.py with forbidden imports | 0 violations |
| NDE-1 | `test_nde1_negative_imports_repository_module` | From core.repository import UserRepository in user_dto.py | 1 violation |
| NDE-1 | `test_nde1_negative_imports_engine_module` | Import core.engine in engine_dto.py | 1 violation |
| NDE-1 | `test_nde1_negative_imports_service_alias` | From core.service import SomeService as Svc in types.py | 1 violation |
| NDE-1 | `test_nde1_regression_spec_example` | MemoryDTO importing Repository | 1 violation |
| NDE-2 | `test_nde2_positive_pydantic_dto` | UserDTO inheriting BaseModel | 0 violations |
| NDE-2 | `test_nde2_positive_non_dto_file_ignored` | utils.py with @dataclass | 0 violations |
| NDE-2 | `test_nde2_negative_uses_dataclass` | @dataclass UserDTO in user_dto.py | 1 violation |
| NDE-2 | `test_nde2_negative_no_base_model` | plain UserDTO in user_dto.py | 1 violation |
| NDE-2 | `test_nde2_negative_mixed_classes` | Good + BadDTO classes | 2 violations |
| NDE-2 | `test_nde2_regression_spec_example` | @dataclass MemoryDTO | 1 violation |
| NDE-3 | `test_nde3_positive_has_schema_version` | UserDTO with schema_version | 0 violations |
| NDE-3 | `test_nde3_positive_non_dto_file_ignored` | utils.py without schema_version | 0 violations |
| NDE-3 | `test_nde3_negative_no_schema_version` | UserDTO missing schema_version | 1 violation |
| NDE-3 | `test_nde3_negative_multiple_dtos_missing` | 2 DTOs missing schema_version | 2 violations |
| NDE-3 | `test_nde3_regression_spec_example` | MemoryDTO missing schema_version | 1 violation |

### NUC Rules (13 tests)
| # | Test | Pattern | Expected |
|---|---|---|---|
| NUC-1 | `test_nuc1_positive_core_safe_imports` | core/utils.py with safe imports | 0 violations |
| NUC-1 | `test_nuc1_positive_non_core_file_ignored` | api/main.py with fastapi | 0 violations |
| NUC-1 | `test_nuc1_negative_imports_fastapi` | core/utils.py importing fastapi | 1 violation |
| NUC-1 | `test_nuc1_negative_imports_starlette` | core/web_utils.py importing starlette | 1 violation |
| NUC-1 | `test_nuc1_negative_imports_click` | core/cli_utils.py importing click | 1 violation |
| NUC-1 | `test_nuc1_negative_imports_typer` | core/cli.py importing typer | 1 violation |
| NUC-1 | `test_nuc1_negative_imports_rich` | core/output.py importing rich | 1 violation |
| NUC-1 | `test_nuc1_negative_imports_textual` | core/ui.py importing textual | 1 violation |
| NUC-1 | `test_nuc1_regression_spec_example` | core/deps.py importing fastapi.Depends | 1 violation |
| NUC-2 | `test_nuc2_positive_core_safe_imports` | core/utils.py with safe imports | 0 violations |
| NUC-2 | `test_nuc2_positive_non_core_file_ignored` | ui/gui.py with tkinter | 0 violations |
| NUC-2 | `test_nuc2_negative_imports_tkinter` | core/gui_utils.py importing tkinter | 1 violation |
| NUC-2 | `test_nuc2_negative_imports_pyqt` | core/ui.py importing PyQt5 | 1 violation |
| NUC-2 | `test_nuc2_negative_imports_kivy` | core/kivy_utils.py importing kivy | 1 violation |
| NUC-2 | `test_nuc2_negative_imports_playwright` | core/browser.py importing playwright | 1 violation |
| NUC-2 | `test_nuc2_regression_spec_example` | core/browser.py importing playwright | 1 violation |

---

## 5. Quality Gate Results

| Check | Command | Result |
|---|---|---|
| Format | `ruff format --check scripts/architecture_linter.py scripts/__init__.py tests/test_architecture_linter.py` | ✅ 3 files already formatted |
| Lint | `ruff check scripts/architecture_linter.py scripts/__init__.py tests/test_architecture_linter.py` | ✅ All checks passed! |
| Types | `mypy --strict scripts/architecture_linter.py` | ✅ Success: no issues found in 1 source file |
| Tests | `pytest tests/test_architecture_linter.py -v` | ✅ **113/113 passed** in 5.12s |

---

## 6. Frozen-Spec Compliance Statement

| Item | Source | Status |
|---|---|---|
| Rule IDs (NDE-1, NDE-2, NDE-3, NUC-1, NUC-2) | spec §3.4 + §3.5 | ✅ Match |
| Severity defaults (ERROR) | spec §4 | ✅ Match |
| DTO file detection (*dto.py, *types.py) | spec §3.4 | ✅ Match |
| Forbidden keywords (NDE-1) | spec §3.4 | ✅ Match (3 keywords, case-insensitive) |
| Forbidden keywords (NUC-1) | spec §3.5 | ✅ Match (7 keywords) |
| Forbidden keywords (NUC-2) | spec §3.5 | ✅ Match (4 keywords, case-insensitive) |
| core/ directory scope (NUC rules) | spec §3.5 | ✅ Match |
| BaseModel requirement (NDE-2) | spec §3.4 | ✅ Match |
| schema_version requirement (NDE-3) | spec §3.4 | ✅ Match |
| File path (no change) | spec §2 | ✅ Match |
| CLI flags (no change) | spec §6 | ✅ Match |
| JSON schema v1.0 (no change) | spec §8 | ✅ Match |
| Exit codes 0/1/2 (no change) | spec §6 | ✅ Match |

**Zero frozen spec deviations.**

---

## 7. Scope Verification — E Did NOT Touch F

| Scope | Touched? | Evidence |
|---|---|---|
| NCP rules (NCP-1..2) | ❌ NO | NCP not registered; not implemented |
| KG stubs (KG-1..7) | ❌ NO | KG disabled in config; not implemented |
| CI integration | ❌ NO | No .github/workflows/* changes |
| Reporter redesign | ❌ NO | TextReporter/JsonReporter unchanged |
| Golden-file tests | ❌ NO | Not added yet |
| Freeze report | ❌ NO | Deferred to F |

**All F scope items remain UNTOUCHED.**

---

## 8. Next Steps (Pending Architect)

Per AGENTS.md §5 Lifecycle, after E approval:
1. **M5.5.1.F** — NCP rules + KG stubs + Reporter hardening + Golden tests + CI integration + Self-dogfooding + Final Freeze

---

**Awaiting architect approval to proceed to M5.5.1.F.**

**Signed off:** Lead Software Architect + Principal QA Engineer (E implementation)
**Date:** 2026-07-04
