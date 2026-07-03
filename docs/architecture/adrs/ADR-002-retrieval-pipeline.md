# ADR-002: Retrieval Pipeline Design

**Status:** Accepted
**Date:** 2026-07-03
**Deciders:** JARVIS Memory Team
**Related:** Phase 19 M4 (Retrieval), spec §6 (Retrieval Pipeline), ADR-001

---

## Context

Phase 19 M4 implements the retrieval pipeline: given a `RetrievalRequest`, return a `RetrievalResponse` with the top-K memory chunks. The pipeline must support:

- **Permission filtering** (visibility, trust level, ACL)
- **Metadata filtering** (type, tier, date range, tags)
- **Scoring** (7-weight formula from spec §3.1)
- **Graph expansion** (Phase 20+ — find related memories via KG)
- **Deduplication** (collapse near-duplicate chunks)
- **Top-K selection** (configurable cap)
- **Event emission** (`memory.retrieve.started/completed/failed`)

Existing patterns in JARVIS (Phase 0-12): mix of ABC and Protocol. Need consistent choice.

## Decision

**We use a hybrid pattern:**

1. **`RetrievalEngine`** — concrete class, owns the pipeline orchestration
2. **`IMemoryRecordRepository`** — ABC injected (read-only, no writes from retrieval)
3. **`ScoringEngine`** — concrete class injected
4. **`CandidateProvider`** — Protocol injected (allows KG, vector DB, hybrid extensions)
5. **`EventBusInterface`** — ABC injected (from `core/interfaces.py`)

All dependencies are **constructor-injected** (no global state, no lazy imports).

### Pipeline Stages (frozen order)

```
RetrievalRequest
   ↓
1. Permission filter       (visibility, trust, ACL)
   ↓
2. Metadata filter         (type, tier, date, tags)
   ↓
3. Candidate fetch         (via CandidateProvider Protocol)
   ↓
4. Score                   (ScoringEngine with 7 weights)
   ↓
5. Graph expansion         (M6, optional, KG plug-in)
   ↓
6. Deduplication           (cosine sim > 0.95 → collapse)
   ↓
7. Top-K selection         (default 10, max 100)
   ↓
8. Event emission          (memory.retrieve.completed)
   ↓
RetrievalResponse
```

## Alternatives Considered

### Option A: Single monolithic function
- **Pros:** Simple, fast
- **Cons:** Hard to test, no extension points, can't swap stages
- **Verdict:** Rejected. Testability is non-negotiable.

### Option B: Pipeline of pure-function stages with no DI
- **Pros:** Functional style, composable
- **Cons:** Hard to share state (scoring weights, config) across stages
- **Verdict:** Rejected. Config injection is required.

### Option C: Strategy pattern (each stage = Strategy)
- **Pros:** Maximum flexibility
- **Cons:** Over-engineering for 8 stages
- **Verdict:** Rejected. YAGNI.

## Consequences

### Positive
- **Testability:** each stage can be unit-tested with mock dependencies
- **Extensibility:** new stages (e.g., re-ranking) added without breaking existing
- **Configurability:** all caps (max_chunks, max_tokens) come from `MemoryConfig`
- **Future-proof:** M6 KG expansion plugs in via `CandidateProvider` Protocol
- **Observability:** events emitted at start/end of each stage (in M5+)

### Negative
- **5 injected dependencies:** verbose constructor, requires discipline
- **Protocol + ABC mix:** need to document when to use which (Rule: ABC for state, Protocol for cross-module)
- **Stage count:** 8 stages is non-trivial; new contributors must understand flow

### Mitigation
- Constructor pattern enforced via type hints (mypy strict)
- Architectural decision documented in this ADR
- Pipeline diagram in `docs/14_MEMORY_ENGINE_FREEZE.md`

## Future Changes

- **M6:** Add `KGCandidateProvider` as a `CandidateProvider` implementation
- **M7+:** May add re-ranking stage (cross-encoder LLM, but this is Phase 20+ LLM work)
- **Phase 24+:** Add `VectorCandidateProvider` for semantic-only retrieval (when LLM-free)

Any change to stage order requires CR (it affects observability and event semantics).

## References

- Phase 19 spec §6 (Retrieval Pipeline)
- `core/memory/retrieval_engine.py` (M4 implementation)
- `core/memory/scoring.py` (M3 scoring engine)
- `core/memory/interfaces.py` (IMemoryRecordRepository, CandidateProvider Protocol)
- ADR-001-memory-storage (storage decision)
- AGENTS.md §7.4 (layer dependency direction)
