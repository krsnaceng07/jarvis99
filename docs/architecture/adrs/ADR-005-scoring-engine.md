# ADR-005: Scoring Engine — 7 Weights and Pure Functions

**Status:** Accepted
**Date:** 2026-07-03
**Deciders:** JARVIS Memory Team
**Related:** Phase 19 M3 (Scoring), spec Â§3.1 (frozen formula), spec Â§3.2 (frozen defaults)

---

## Context

Phase 19 M3 implements memory scoring. The scoring formula determines which memories are "important" and surface in retrieval. The spec Â§3.1 **freezes** the formula:

```
FinalScore = w_recency * Recency
           + w_semantic * SemanticSimilarity
           + w_confidence * Confidence
           + w_importance * Importance
           + w_frequency * Frequency
           + w_trust * Trust
           + w_pin * UserPin
```

**7 weights**, all configurable, with **default values** in spec Â§3.2:
- w_recency=0.25, w_semantic=0.20, w_confidence=0.20, w_importance=0.15, w_frequency=0.10, w_trust=0.05, w_pin=0.05

This ADR documents **why 7 weights** (not 3, not 10) and **why pure functions** (no side effects).

## Decision

### 1. Seven Weights, Not Three

The 7 weights cover the **7 distinct dimensions of memory importance** that JARVIS must evaluate:

| Weight | What it measures | Why needed |
|---|---|---|
| `w_recency` | Time decay | Recent memories more relevant for active tasks |
| `w_semantic` | Vector similarity to query | Semantic relevance is core to retrieval |
| `w_confidence` | Source reliability | Low-confidence memories are noise |
| `w_importance` | User/system mark | Some memories are inherently important |
| `w_frequency` | Access count | Frequently accessed = high utility |
| `w_trust` | Trust level (USER/SYSTEM/AGENT) | Source matters |
| `w_pin` | User pin (1.0 boost) | Pinned memories always surface |

**Why not 3?** Three weights (e.g., recency + relevance + importance) would conflate distinct concerns. `w_semantic` is query-dependent, `w_recency` is time-dependent, `w_importance` is metadata â€” merging them loses signal.

**Why not 10?** Each additional weight adds:
- Config complexity (operators tune 7 vs 10 vs 3)
- Test surface (each weight needs boundary tests)
- Documentation burden (7 docs vs 10)

7 is the **minimum that captures all distinct signals** identified in user research (Phase 1-12 traces). Adding an 8th requires **evidence of a new signal not covered by current 7**.

### 2. Pure Functions, No Side Effects

`ScoringEngine` has:
- **No IO** (no DB, no network, no EventBus)
- **No global state** (weights injected via `MemoryScoringConfig`)
- **No mutation** (returns new `MemoryScore` Pydantic model)
- **No LLM calls** (semantic similarity comes from pre-computed embeddings)

This makes scoring:
- **Deterministic** (same input â†’ same output, always)
- **Trivially testable** (no mocks, no fixtures)
- **Cacheable** (pure function memoization is safe)
- **Parallelizable** (no shared state)

## Alternatives Considered

### Option A: 3 weights (recency, relevance, importance)
- **Pros:** Simpler config
- **Cons:** Loses signal â€” confidence, trust, frequency all conflated
- **Verdict:** Rejected. Quality regression in retrieval precision.

### Option B: 10 weights (split w_pin into w_manual_pin + w_auto_pin)
- **Pros:** More granular control
- **Cons:** Over-engineering, no evidence of need
- **Verdict:** Rejected. YAGNI. Can add later if evidence emerges.

### Option C: LLM-based scoring (use LLM to score each memory)
- **Pros:** Adaptive, can learn
- **Cons:** Non-deterministic, expensive (latency + cost), requires LLM
- **Verdict:** Rejected. Violates "no LLM in scoring" layer rule (AGENTS.md Â§7.4). Pure function is non-negotiable for reproducibility.

### Option D: ML model (train on user feedback)
- **Pros:** Personalized
- **Cons:** Cold start, training data needed, MLOps complexity
- **Verdict:** Deferred to Phase 20+. Current rule-based formula is interpretable + adjustable.

## Consequences

### Positive
- **Reproducible:** same query + same memory â†’ same score, every time
- **Tunable:** operators adjust 7 weights without code change (just config)
- **Auditable:** formula is in spec, no hidden behavior
- **Fast:** pure function, ~1ms per score
- **Cacheable:** result memoization safe (e.g., 1000 chunk query â†’ 1000 scores â†’ cache)

### Negative
- **Static weights:** no per-user or per-context adaptation
- **No learning:** user feedback not used to improve
- **Manual tuning required:** operators must experiment

### Mitigation
- Config is environment-specific (dev, staging, prod can differ)
- A/B testing of weight configs supported via `MemoryScoringConfig` variants
- Phase 20+ may add ML-based re-ranker as separate stage (not in scoring engine)

## Future Changes

- **Phase 20+:** May add ML-based re-ranking stage (after rule-based scoring)
- **Phase 24+:** May add per-user weight adaptation (if evidence supports)
- **Possible:** Split `w_pin` into `w_manual_pin` and `w_auto_pin` if use case emerges

Any change to the 7 weights (add/remove/rename) requires:
1. New spec Â§3.1 with CR
2. ADR supersession
3. Migration of all `MemoryScoringConfig` instances

## References

- Phase 19 spec Â§3.1 (frozen formula)
- Phase 19 spec Â§3.2 (frozen defaults)
- `core/memory/scoring.py` (M3 implementation)
- `core/config.py` (MemoryScoringConfig, Pydantic wrapper)
- AGENTS.md Â§7.6 (compiled objects, DTOs, frozen specs are immutable)
- AGENTS.md Â§7.4 (no LLM in scoring â€” layer rule)
