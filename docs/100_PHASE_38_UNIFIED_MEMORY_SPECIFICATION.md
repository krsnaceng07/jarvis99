# 100_PHASE_38_UNIFIED_MEMORY_SPECIFICATION.md

## Purpose
This document establishes the architecture specification for **Phase 38: Unified Memory & Knowledge Graph**. It defines the cognitive memory layers (Working, Long-Term, Episodic, Semantic, Procedural) and Knowledge Graph entities to serve as context assets for the Brain Kernel.

## Status
**STATUS:** DRAFT (Awaiting Approval)
**Authority:** Rank 4 (Phase Specification)
**Dependencies:** Phase 37

---

## 1. Architectural Position

The Memory Subsystem integrates directly with `BrainKernel` to provide context assembly, semantic retrieval, and experience recording:

```
               [ Brain Kernel ]
                      │
        ┌─────────────┴─────────────┐
        ▼                           ▼
  [ Neural Layer ]           [ Memory Layer ]
                      ┌─────────────┼─────────────┐
                      ▼             ▼             ▼
                 [ Episodic ]   [ Semantic ]  [ Procedural ]
                      └─────────────┬─────────────┘
                                    ▼
                           [ Knowledge Graph ]
```

---

## 2. Directory Layout & Structure

```text
core/memory/
  ├── working_memory.py      # Transient context window manager
  ├── long_term_memory.py    # Persistent semantic/episodic storage interface
  ├── knowledge_graph.py     # Entities, relations, and triple indexer
  ├── consolidation.py       # Asynchronous offline context aggregator
  └── context_assembly.py    # BrainKernel context packager
```

---

## 3. Component Contracts

### 3.1 Memory Layers

```python
class UnifiedMemoryManager:
    """Coordinates Working, Episodic, Semantic, and Procedural Memory stores."""

    async def query(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Perform semantic search across all persistent memory layers."""

    async def write_episodic(self, experience: Dict[str, Any]) -> None:
        """Write execution record to episodic memory database."""
```

### 3.2 Knowledge Graph

```python
class KnowledgeGraph:
    """Manages entity nodes, relationships, and property graphs."""

    async def add_entity(self, name: str, entity_type: str, properties: Dict[str, Any]) -> None:
        """Create or update a graph node entity."""

    async def add_relation(self, source: str, target: str, rel_type: str) -> None:
        """Define a relationship link between two entities."""
```

---

## 4. Verification and Acceptance Criteria
- **Semantic Retrieval**: Verify query requests match relevant semantic text records using vector similarities.
- **Consolidation Cycle**: Verify episodic memory records consolidate successfully into semantic entity triples.
