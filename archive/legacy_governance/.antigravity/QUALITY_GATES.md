# QUALITY GATES

## 1. Mandatory Quality Gates Table
Every milestone and phase completion checklist requires all of the following validations to pass successfully:

| Gate | Target Metric | Command / Tool | Action on Failure |
| --- | --- | --- | --- |
| **Format** | Clean formatting | `ruff format --check` | Block Build / Merge |
| **Lint** | Zero errors/warnings | `ruff check` | Block Build / Merge |
| **Types** | Strict type compliance | `mypy --strict` | Block Build / Merge |
| **Tests** | All tests pass, no regressions | `pytest` | Block Build / Merge |
| **Coverage** | **≥ 80%** general, **100%** security | `pytest --cov` | Block Build / Merge |
| **Architecture Audit** | Zero cycle or layer violations | Dependency graph checker | Block Build / Merge |
| **Governance Audit** | SRP, no hidden state, interface compliance | Manual / Automated check | Block Build / Merge |
| **Doc Audit** | Master Index & Status Board updated | Navigation check | Block Build / Merge |

---

## 2. Tooling Configuration Specifications
* **Ruff Layout:** Maximum line length of 88 characters. Selects standard errors/warnings (`E`, `F`, `W`, `I`).
* **Mypy strict mode:** `strict = true` in config file (`pyproject.toml`). All function inputs, outputs, and variables must have explicit type annotations.
* **Pytest mode:** `asyncio_mode = auto`. All database or service fixtures must run within clean test transactions.

---

## 3. Mini Quality Gate vs Final Quality Gate

### Mini Quality Gate (Run on each commit/milestone):
1. Execute `ruff format` on affected files.
2. Execute `ruff check` on affected files.
3. Run `mypy` on the modified module.
4. Run `pytest` targeting the modified component's tests.
5. Verify coverage for the target module satisfies threshold checks.

### Final Quality Gate (Run before Spec Freeze & Merge):
1. Execute full codebase format/lint validation.
2. Run full codebase `mypy` check.
3. Execute the entire `pytest` suite.
4. Verify total codebase test coverage is $\ge 80\%$.
5. Confirm security module coverage remains at $100\%$.
6. Run architecture cycle and layer checks.
7. Record final test counts in the Phase Status Board.
