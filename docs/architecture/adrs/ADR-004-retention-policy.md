# ADR-004: Retention Policy — Promotion, Forgetting, Throttle, Cascade

**Status:** Accepted
**Date:** 2026-07-03
**Deciders:** JARVIS Memory Team
**Related:** Phase 19 M5 (Retention), spec §8.2 (Retention Engine), §8.4 (MemoryRetentionConfig)

---

## Context

Phase 19 M5 implements the Retention Engine. Memory has 3 tiers (WORKING → CONVERSATION → LONG_TERM), and chunks need to be:
- **Promoted** to a warmer tier when access/score thresholds are met
- **Forgotten** (soft-deleted) when TTL expires, score decays, or user requests
- **Archived** (after 30 days) for compliance / cold storage
- **Cascade-deleted** when source memory is removed
- **Throttled** to prevent promotion storms (max 1 promotion/memory/60s)

The retention engine must:
- Be **idempotent** (re-evaluation produces same actions, no duplicate promotions)
- Be **atomic** (cascade deletes are all-or-nothing)
- Emit **events** AFTER writes (`memory.promoted`, `memory.archived`, `memory.deleted`)
- **Not contain business logic** (engine proposes actions, orchestrator executes)

## Decision

### 1. Engine Proposes, Orchestrator Disposes

`RetentionEngine.evaluate(now)` returns a `RetentionEvaluationResult` containing lists of `PromotionAction` and `ForgettingAction`. It does **not** write to the repository.

The **Memory Orchestrator** (M7) is responsible for:
- Calling `engine.evaluate()`
- Validating each action (idempotency check, version check)
- Writing to repository via transaction
- Emitting events AFTER write commit

This separation:
- Keeps `RetentionEngine` pure and testable (no IO, no events)
- Allows the orchestrator to batch / schedule / retry
- Preserves the "engine proposes, orchestrator disposes" pattern (AGENTS.md §7.10)

### 2. Throttle: 60s Per Memory

Maximum **1 promotion per memory per 60 seconds** (configurable via `MemoryRetentionConfig.promotion_throttle_seconds`).

**Why 60s?**
- Prevents promotion storms (e.g., a memory accessed 1000 times in 1 second)
- Gives the system time to stabilize between promotions
- Configurable if user research shows different cadence

Throttle is enforced by the **engine** (not the orchestrator) because:
- Engine sees all candidate promotions
- Throttle check is part of "is this promotion valid?" logic
- Orchestrator just executes what engine produces

### 3. Cascade: All-or-Nothing

When a memory is deleted (reason="cascade"), all incident edges (in M6 KG) and related memories (Phase 20+) are soft-deleted in a **single transaction**.

**Why all-or-nothing?**
- Partial deletion creates orphans (edge without node)
- Inconsistent state is worse than no state
- ACID guarantees via Postgres transaction

**Why soft-delete (not hard-delete)?**
- Reversibility (admin can restore from archive)
- Audit trail (who deleted what, when)
- GDPR compliance (right to erasure preserved in audit log)

### 4. Archive: 30-Day Retention

Soft-deleted memories are moved to `archive` table after 30 days. Original record is hard-deleted from active tables.

**Why 30 days?**
- Compliance baseline (GDPR, CCPA grace period)
- Recovery window (user changes mind)
- Storage cost (active DB smaller, cheaper queries)

## Alternatives Considered

### Option A: Engine writes directly (no orchestrator)
- **Pros:** Simpler, fewer layers
- **Cons:** Engine contains IO, harder to test, no batching
- **Verdict:** Rejected. Violates "engine proposes" pattern.

### Option B: No throttle (every access promotes)
- **Pros:** Real-time promotion
- **Cons:** Promotion storms, DB thrashing, no stabilization
- **Verdict:** Rejected. Untestable in production.

### Option C: Hard delete on cascade
- **Pros:** No archive overhead
- **Cons:** No recovery, no audit, GDPR right-to-erasure breaks
- **Verdict:** Rejected. Compliance risk.

### Option D: Hard delete after 7 days (faster cleanup)
- **Pros:** Smaller active DB
- **Cons:** Less recovery window, may violate some compliance regimes
- **Verdict:** Rejected. 30 days is conservative baseline.

## Consequences

### Positive
- **Testable:** `RetentionEngine` is pure, tested with deterministic inputs
- **Reversible:** soft-delete + 30-day archive = safety net
- **Auditable:** every promotion/forgetting event has `reason` and `actor`
- **Bounded:** throttle prevents runaway

### Negative
- **Two-phase commit:** engine proposes, orchestrator executes → not atomic across the boundary
- **30-day storage:** active DB may grow if many soft-deletes
- **Throttle may delay legitimate promotions:** a memory accessed 5 times in 60s only promotes once

### Mitigation
- Orchestrator can batch + retry the engine output (idempotency preserves safety)
- Active DB has soft-delete cleanup job (Phase 20+)
- Throttle is configurable per environment (dev: 10s, prod: 60s)

## Future Changes

- **Phase 20+:** May add per-tier TTL (currently L1=10min, L2=24h, L3=indefinite)
- **Phase 24+:** May add ML-based promotion (predict importance, not just access count)
- **Possible:** Increase archive retention for compliance-sensitive domains (healthcare: 7 years)

Any change to throttle, cascade, or archive retention requires CR.

## References

- Phase 19 spec §8.2 (Retention Engine)
- Phase 19 spec §8.4 (MemoryRetentionConfig)
- `core/memory/dto.py` (PromotionAction, ForgettingAction, RetentionEvaluationResult)
- `core/config.py` (MemoryRetentionConfig)
- AGENTS.md §7.10 (Orchestrator coordinates; never bypasses; engine proposes)
- ADR-001-memory-storage (storage strategy)
