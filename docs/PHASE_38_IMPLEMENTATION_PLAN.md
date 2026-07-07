# PHASE_38_IMPLEMENTATION_PLAN.md

## Purpose
This document outlines the detailed implementation checkpoints for **Phase 38: Unified Memory & Knowledge Graph**, covering episodic write pipelines, semantic graphs, and consolidation workers.

## Status
**STATUS:** DRAFT (Awaiting Approval)
**Authority:** Rank 5 (Implementation Plan)
**Dependencies:** Phase 37

---

## 1. Planned Changes

| Component | Target File | Responsibility |
| --------- | ----------- | -------------- |
| **Working Memory** | `core/memory/working_memory.py` | Transient memory storage manager. |
| **Long-Term Memory** | `core/memory/long_term_memory.py` | Persistent episodic/semantic vector router. |
| **Knowledge Graph** | `core/memory/knowledge_graph.py` | Triple graphs store and relations indexer. |
| **Consolidation** | `core/memory/consolidation.py` | Consolidates episodic data into long-term records. |
| **Integration** | `core/kernel.py` | Wire memory components into DI container. |
| **Verification** | `tests/test_unified_memory.py` | Memory query and consolidation verification. |

---

## 2. Milestones and Quality Gates

### Milestone 1: Memory Layer Core & DI Setup
- Implement `working_memory.py` and `long_term_memory.py`.
- Register components inside `core/kernel.py`.
- **Mini-Quality Gate**: `ruff check`, `mypy` on added files.

### Milestone 2: Knowledge Graph & Relations
- Implement entity and relations triple indexing in `knowledge_graph.py`.
- **Mini-Quality Gate**: `ruff check`, `mypy` on added files.

### Milestone 3: Consolidation Cycle
- Implement consolidation algorithms in `consolidation.py`.
- **Mini-Quality Gate**: `ruff check`, `mypy` on added files.

### Milestone 4: Verification & Quality Gates
- Create `tests/test_unified_memory.py` testing retrieval layers.
- **Final Quality Gate**: `python scripts/quality_gate.py` passes cleanly.
