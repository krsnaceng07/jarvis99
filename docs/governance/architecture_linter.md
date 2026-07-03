# Architecture Linter — Governance System

**Status:** ✅ FROZEN — 2026-07-03 (M5.5.0)
**Version:** 1.0
**Date opened:** 2026-07-03
**Frozen by:** M5.5.0 (Engineering Governance Freeze)
**Authority:** AGENTS.md §4 (Frozen Architecture Boundaries), §7.4 (Dependency Direction), Quality Gates Engine Gate 1
**Related:** Dependency Graph Validator, Quality Gates Engine, QGE Gate 1

---

## 1. Purpose

The Architecture Linter is a **custom static-analysis tool** that enforces architectural rules that generic linters (ruff, mypy) cannot express: layer direction, forbidden imports, business-logic-in-repository, side-effects-in-decision-engine, etc.

**Rule:** Every PR MUST pass the Architecture Linter with zero violations. There is no override flag (per [quality_gates_engine.md §6](quality_gates_engine.md#6-no-manual-bypass)).

---

## 2. Tooling

- **Implementation:** Custom Python script `scripts/architecture_linter.py` (uses `ast` module to parse imports + class structure).
- **Alternative:** [`import-linter`](https://github.com/seddonym/import-linter) — vendored, configured via `.importlinter`.
- **Integration:** Runs as Quality Gate 1 (Architecture) in the QGE.

---

## 3. Rule Categories

### 3.1 Layer Direction Rules (LR)

| ID | Rule | Example violation |
|---|---|---|
| **LR-1** | `core/` MUST NOT import from `api/`, `cli/`, `ui/` | `from api.routes import foo` in `core/memory/kg.py` |
| **LR-2** | `api/` MUST NOT import implementation details from `core/<subsystem>/` private files | `from core.memory._private import util` |
| **LR-3** | `ui/` MUST NOT import directly from `core/` — go through `api/` | `from core.brain import Brain` in `ui/components/chat.py` |
| **LR-4** | `cli/` MUST NOT import from `api/` or `ui/` — go through `core/` | `from api.main import app` in `cli/main.py` |
| **LR-5** | Layer direction: `UI → API → Brain → {Memory, Tools} → Infrastructure` | Any reverse direction |

### 3.2 No Business Logic in Repository (NBR)

| ID | Rule | Example violation |
|---|---|---|
| **NBR-1** | A class named `*Repository` MUST NOT contain methods with `def` names suggesting business logic (`process_*`, `decide_*`, `validate_*`, `score_*`, `rank_*`, `recommend_*`) | `def score_memory(...)` in `MemoryRepository` |
| **NBR-2** | A class named `*Repository` MUST NOT call an LLM, an embedding model, or any planner | `await llm.generate(...)` inside `Repository.create()` |
| **NBR-3** | A class named `*Repository` MUST NOT write to the event bus directly — must return data for the orchestrator to publish | `await bus.publish(...)` inside `Repository.update()` |
| **NBR-4** | A class named `*Repository` MUST NOT perform `merge()` of graph nodes (that's a `KGService` concern) | `def merge_nodes(...)` in `KGRepository` |

### 3.3 No Side Effects in Decision Engine (NSD)

| ID | Rule | Example violation |
|---|---|---|
| **NSD-1** | A class named `*Engine` (decision, inference, scoring) MUST NOT perform DB writes | `await db.execute(...)` in `InferenceEngine.infer()` |
| **NSD-2** | A class named `*Engine` MUST NOT mutate its inputs (inputs are immutable DTOs) | `node.properties["x"] = 1` in `TraversalEngine` |
| **NSD-3** | A class named `*Engine` MUST NOT call tools or external services | `await tool.execute(...)` in `ScoringEngine` |

### 3.4 No DTO in Repository / Engine (NDE)

| ID | Rule | Example violation |
|---|---|---|
| **NDE-1** | DTO files (`*dto.py`, `*types.py`) MUST NOT import from `Repository`, `Engine`, or `Service` | `from core.memory.repository import MemoryRepository` in `dto.py` |
| **NDE-2** | DTOs MUST be `BaseModel` (Pydantic), not `@dataclass` | `@dataclass class MemoryRecord` |
| **NDE-3** | DTOs MUST carry `schema_version: Literal["X.Y"]` field | DTO without `schema_version` |

### 3.5 No UI in Core (NUC)

| ID | Rule | Example violation |
|---|---|---|
| **NUC-1** | `core/` MUST NOT import from `fastapi`, `starlette`, `flask`, `click`, `typer`, `rich`, `textual` | `from fastapi import HTTPException` in `core/memory/kg_service.py` |
| **NUC-2** | `core/` MUST NOT import from `tkinter`, `pyqt`, `kivy`, `playwright` | `from playwright.sync_api import sync_playwright` in `core/` |

### 3.6 No Cross-Phase Imports (NCP)

| ID | Rule | Example violation |
|---|---|---|
| **NCP-1** | A frozen phase (1-13) MUST NOT import from a non-frozen phase (14+) | `from core.phase14.api_gateway import X` in `core/phase13/auth/` |
| **NCP-2** | A future phase (20+) MUST NOT import from a non-yet-existing module | forward references (caught by mypy) |

---

## 4. Rule Severity

| Severity | Effect |
|---|---|
| **ERROR** | Blocks merge. Must fix. |
| **WARN** | Logs warning. Must add justification comment or fix. |
| **INFO** | Logs info only. No action required. |

Default severity for all rules above: **ERROR**.

---

## 5. M6-Specific Rules

For the Knowledge Graph milestone, the following are added:

| ID | Rule |
|---|---|
| **KG-1** | `core/memory/kg/inference_engine.py` MUST NOT call `await db.execute(...)` |
| **KG-2** | `core/memory/kg/repository.py` MUST NOT call LLM/embedding |
| **KG-3** | `core/memory/kg/service.py` MUST NOT bypass `IKGRepository` (no direct SQL) |
| **KG-4** | `core/memory/kg/dto.py` MUST NOT import from `service.py` or `repository.py` |
| **KG-5** | `api/`, `cli/`, `ui/` MUST NOT import from `core/memory/kg/` directly |
| **KG-6** | `TraversalEngine` MUST NOT write to `kg_nodes` or `kg_edges` tables |
| **KG-7** | `InferenceEngine` MUST NOT write to any table |

---

## 6. Implementation Sketch (no code yet)

```python
# scripts/architecture_linter.py
# Pseudocode only — actual code is M5.5.x milestone deliverable.

class ArchitectureLinter:
    def __init__(self, repo_path: Path, config: LinterConfig): ...
    def lint(self) -> List[Violation]: ...
    def report(self) -> str: ...

# CLI:
#   python -m scripts.architecture_linter --config .architecture-linter.toml
# Exit code 0 = pass, 1 = violations found.
```

---

## 7. Configuration File

`.architecture-linter.toml`:

```toml
[general]
severity_default = "error"
exclude = ["tests/", "archive/", "scripts/"]

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
enabled = true
severity = "error"
```

---

## 8. Versioning

- v1.0 (2026-07-03): 6 rule categories, 30+ individual rules, M6-specific ruleset.
