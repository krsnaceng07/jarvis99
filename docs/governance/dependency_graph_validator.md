# Dependency Graph Validator (DGV) — Governance System

**Status:** ✅ FROZEN — 2026-07-03 (M5.5.0)
**Version:** 1.0
**Date opened:** 2026-07-03
**Frozen by:** M5.5.0 (Engineering Governance Freeze)
**Authority:** AGENTS.md §7.4 (Dependency Direction), Quality Gates Engine Gate 1
**Related:** Architecture Linter, Quality Gates Engine

---

## 1. Purpose

The Dependency Graph Validator (DGV) builds the **module-level dependency graph** of the JARVIS codebase and validates it against architectural rules: no cycles, correct layer direction, no forbidden connections.

**Rule:** Every PR MUST pass the DGV. A cycle or forbidden connection is a hard merge block.

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  DGV (scripts/dgv.py)                    │
└────────────┬────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────┐
│  1. Parse: AST-scan every .py file                       │
│     Build graph: G = (V modules, E imports)              │
└────────────┬────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────┐
│  2. Validate:                                            │
│     a. Cycle detection (Tarjan's SCC)                    │
│     b. Layer direction (topological order check)         │
│     c. Forbidden connections (rule list)                 │
│     d. Stable topological sort exists? (no cycles)       │
└────────────┬────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────┐
│  3. Report:                                              │
│     - Graph as DOT/PNG (committed to docs/diagrams/)    │
│     - Violations list                                    │
│     - Layer summary (which modules are in which layer)   │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Tooling

- **Implementation:** Custom Python script `scripts/dgv.py`.
- **Inputs:** All `.py` files under `core/`, `api/`, `cli/`, `ui/`, `tests/`.
- **Output:**
  - `docs/diagrams/dependency_graph.dot` (Graphviz)
  - `docs/diagrams/dependency_graph.png` (rendered, on CI)
  - `docs/diagrams/dependency_summary.json` (machine-readable)
- **Algorithm:** Tarjan's strongly-connected-components for cycle detection.

---

## 4. Validation Rules

### 4.1 Cycle Detection

- **Algorithm:** Tarjan's SCC. Any SCC with size > 1 (or self-loop) is a cycle.
- **Severity:** ERROR.
- **Output:** List of cycles with file paths.

### 4.2 Layer Direction (LDR)

- **Expected layer order:** `ui → api → brain → {memory, tools} → infrastructure → {external}`
- **Algorithm:** Compute topological order; any edge that points "upward" (against the layer order) is a violation.
- **Severity:** ERROR.
- **Layer assignment:** Determined by file path prefix:
  - `ui/` → UI layer
  - `api/` → API layer
  - `core/brain/`, `core/orchestrator/`, `core/planner/` → Brain layer
  - `core/memory/`, `core/tools/`, `core/skills/`, `core/agents/` → Domain layer
  - `core/db/`, `core/events/`, `core/config.py` → Infrastructure layer
  - third-party packages → External

### 4.3 Forbidden Connections (FC)

| From | To | Severity | Reason |
|---|---|---|---|
| `ui/*` | `core/*` (direct) | ERROR | Must go through `api/` |
| `api/*` | `core/memory/_private` | ERROR | Private modules are internal |
| `core/memory/*` | `core/browser/*`, `core/desktop/*` | ERROR | Cross-subsystem leakage |
| `core/memory/*` | `core/llm/*` | ERROR | KG/Repository has no LLM logic |
| `core/llm/*` | `core/memory/*` | ERROR | LLM doesn't depend on storage |
| `core/planner/*` | `core/agents/*` | ERROR | Planner is upstream of agents |
| `core/*` | `api/*`, `cli/*`, `ui/*` | ERROR | Layer reversal |
| any | `archive/*` | ERROR | Archive is read-only history |

### 4.4 Orphan Detection (OD)

- **Rule:** Every public module (file with `__all__`) must be imported by at least one other module.
- **Severity:** WARN (orphan modules may indicate dead code or missing integration).

### 4.5 Coupling Threshold (CT)

- **Rule:** A single module's import count (fan-in + fan-out) must be ≤ 50.
- **Severity:** WARN (high coupling is a smell, not an error).

---

## 5. Expected Dependency Graph (M6)

After M6 is complete, the expected graph is:

```
                ┌──────────────┐
                │     ui/      │
                └──────┬───────┘
                       │
                       ▼
                ┌──────────────┐
                │     api/     │
                └──────┬───────┘
                       │
                       ▼
            ┌──────────────────────┐
            │  core/brain/         │
            │  (orchestrator,      │
            │   planner)           │
            └──────┬───────────────┘
                   │
        ┌──────────┼──────────┬──────────┐
        ▼          ▼          ▼          ▼
  ┌──────────┐ ┌────────┐ ┌────────┐ ┌─────────┐
  │core/     │ │core/   │ │core/   │ │core/    │
  │memory/   │ │tools/  │ │skills/ │ │agents/  │
  │(kg, ret, │ │        │ │        │ │         │
  │ scoring, │ │        │ │        │ │         │
  │ retent)  │ │        │ │        │ │         │
  └────┬─────┘ └────┬───┘ └────────┘ └─────────┘
       │            │
       ▼            ▼
  ┌──────────────────────────┐
  │   core/infrastructure/   │
  │   (db, events, config)   │
  └──────────────────────────┘
```

**No edges between `core/memory/` and `core/llm/`, `core/browser/`, `core/desktop/`, `core/voice/`, `core/vision/`, `core/planner/`, `core/agents/`, `core/workflow/`.**

---

## 6. CI Integration

DGV runs as part of the QGE Gate 1 (Architecture). On every PR:

1. Compute current graph.
2. Compare against expected graph.
3. Run all validation rules.
4. Render PNG and attach to PR.
5. Block merge on any ERROR.

The expected graph is stored in `docs/diagrams/expected_graph.json` and version-controlled. Any intentional graph change requires a CR.

---

## 7. Failure Examples

### 7.1 Cycle

```
core/memory/kg/service.py
  → core/memory/kg/repository.py
  → core/memory/kg/validator.py
  → core/memory/kg/service.py   ← CYCLE
```

**Violation:** `Cycle detected: kg.service → kg.repository → kg.validator → kg.service`

### 7.2 Layer Reversal

```
core/memory/kg/service.py
  → api/main.py
```

**Violation:** `core/ cannot import from api/. Edge: kg.service → api.main`

### 7.3 Forbidden Connection

```
core/memory/kg/repository.py
  → core/llm/embeddings.py
```

**Violation:** `core/memory/* cannot depend on core/llm/*. Edge: kg.repository → llm.embeddings`

---

## 8. Versioning

- v1.0 (2026-07-03): DGV introduced. Layer model, forbidden connections, M6 expected graph.
