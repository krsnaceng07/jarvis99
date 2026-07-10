# ADR-003: Tiered Memory Architecture & Promotion

## Status
* **Status:** Accepted
* **Date:** 2026-07-02
* **Author:** Architecture Team

---

## Context
A flat memory repository creates query performance bottlenecks and fails to reflect human context prioritization. We need hot cache lookups, session-scoped conversation streams, long-term persistence, and relational linkages.

---

## Decision
Establish the Tiered Memory Architecture with four active tiers:
1. **L0 (Identity):** Immutable system constants and user facts.
2. **L1 (Working):** Fast in-process LRU cache (10-minute TTL, max 50 items).
3. **L2 (Conversation):** Session-scoped conversation records (24-hour TTL, max 200 items).
4. **L3 (Long-Term):** Scored, vector-indexed relational storage (30-day default TTL, decayed by importance).

* **Promotion Policy:** Directional flow managed by the `RetentionEngine` based on access frequency or composite scoring.
* **Scoring Formula:** Composite metric combining recency, semantic similarity, confidence, importance, frequency, trust, and pinning.

---

## Consequences
* **Positive:** Hot items stay fast in-memory; low-value records decay and auto-archive safely.
* **Negative:** Requires active indexing pipelines (vector + graph) and throttling to prevent promotion storms.

---

## Compliance & Invariants
* All memory operations must go through the unified `MemoryOrchestrator` interface.
* Vector generation is triggered automatically only when a record reaches the L3 persistent storage.
