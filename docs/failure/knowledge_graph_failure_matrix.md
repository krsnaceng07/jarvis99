# Knowledge Graph Failure Matrix (M6)

**Status:** PROPOSED (freeze before M6.0 implementation)
**Date:** 2026-07-03
**Owner:** Memory subsystem
**Related:** knowledge_graph_contract.md, ADR-001-Knowledge-Graph-Storage.md

---

## Failure Mode Taxonomy

| Severity | Definition | Response Time | Recovery |
|---|---|---|---|
| **CRITICAL** | Service unavailable, data corruption | <1min | Auto-rollback + alert |
| **HIGH** | Single operation failure, partial data inconsistency | <5min | Auto-retry + alert |
| **MEDIUM** | Degraded performance, edge case not handled | <1hr | Log + ticket |
| **LOW** | Cosmetic, observability gap | <1day | Backlog |

---

## 1. Repository Failures (Postgres)

### 1.1 Postgres Unavailable
- **Severity:** CRITICAL
- **Detection:** Connection error, asyncpg `ConnectionRefusedError`
- **Impact:** All KG operations fail
- **Mitigation:**
  - Connection pool with health check (every 30s)
  - Circuit breaker (open after 3 consecutive failures, half-open after 60s)
  - Fail-closed: return `RepositoryUnavailableError` to caller
- **Recovery:**
  - Pool reconnection on next request
  - Cache last-known-good node/edge data in LRU (in-memory, 1000 entries) for read-only fallback
  - When circuit half-opens, send 1 probe request; on success, close
- **Test:** M6.7 (Failure Injection)

### 1.2 Postgres Slow (high latency, not down)
- **Severity:** HIGH
- **Detection:** Query latency > frozen budget p99 for >60s
- **Impact:** User-visible slowness
- **Mitigation:**
  - Query timeout (5s default, per contract §6)
  - Auto-cancel long queries
  - Metric `kg.query.timeout.count` increments
- **Recovery:**
  - Alert on-call
  - Investigate slow query log
  - If persistent, lower `max_depth` config or add index
- **Test:** M6.7 + load test

### 1.3 Disk Full
- **Severity:** CRITICAL
- **Detection:** Postgres `DiskFull` error, write failures
- **Impact:** All writes fail; reads may succeed
- **Mitigation:**
  - Read-only mode (orchestrator knows from `KGNode.archived` or system event)
  - Surface to caller as `RepositoryUnavailableError`
- **Recovery:**
  - Ops expands volume
  - On successful write, resume normal mode
- **Test:** M6.7 (mock disk-full error)

## 2. Concurrency Failures

### 2.1 Optimistic Concurrency Mismatch
- **Severity:** HIGH (expected, normal in distributed systems)
- **Detection:** `UPDATE ... WHERE version = X` returns 0 rows
- **Impact:** Single update fails
- **Mitigation:**
  - Caller passes `expected_version`; repo raises `ConcurrentUpdateError`
  - Caller (orchestrator) may retry with re-read + merge logic
- **Recovery:**
  - Retry policy: max 3 attempts with exponential backoff (50ms, 200ms, 1s)
  - After 3 fails, return error to user agent
- **Test:** M6.7 (concurrent update test)

### 2.2 Deadlock (rare for KG tables, but possible with multiple edges)
- **Severity:** MEDIUM
- **Detection:** Postgres deadlock detector, `DeadlockDetected` exception
- **Impact:** Transaction abort
- **Mitigation:**
  - Postgres handles rollback automatically
  - Repo translates to `RepositoryUnavailableError`
- **Recovery:**
  - Caller retries entire operation
- **Test:** M6.7 (concurrent edge create test)

### 2.3 Duplicate Edge
- **Severity:** LOW (idempotency violation by caller)
- **Detection:** UNIQUE constraint on `(source_id, target_id, type)` (excluding soft-deleted)
- **Impact:** Single create_edge fails
- **Mitigation:**
  - Repo returns existing edge (idempotent) instead of error
  - No exception raised; log info
- **Recovery:** N/A
- **Test:** M6.7

## 3. Data Integrity Failures

### 3.1 Orphan Edge (edge references missing node)
- **Severity:** HIGH
- **Detection:** Foreign key violation on insert; periodic audit query
- **Impact:** Edge cannot be created
- **Mitigation:**
  - DB-level FK constraint (`source_id REFERENCES kg_nodes(id)`, `target_id REFERENCES kg_nodes(id)`)
  - Periodic audit (daily): `SELECT * FROM kg_edges WHERE NOT EXISTS (SELECT 1 FROM kg_nodes WHERE id = source_id)`
- **Recovery:**
  - On insert fail: return `NodeNotFoundError`
  - On audit find: alert + manual cleanup; do not auto-delete
- **Test:** M6.7

### 3.2 Corrupted Properties JSON
- **Severity:** MEDIUM
- **Detection:** Pydantic validation fails on read
- **Impact:** Single node/edge cannot be read
- **Mitigation:**
  - Read returns `Optional[KGNode] = None` + log warning
  - Metric `kg.node.corrupted.count` increments
- **Recovery:**
  - Mark as quarantined (system event `kg.node.quarantined`)
  - Manual review by ops
  - Do not auto-delete; preserve for forensics
- **Test:** M6.7 (corrupt JSON fixture)

### 3.3 Cycle in Graph (logical, not data corruption)
- **Severity:** LOW (graphs can have cycles legitimately)
- **Detection:** Explicit `cycle_detected` check in `find_path` with `find_shortest_path` semantics
- **Impact:** Path-finding may loop
- **Mitigation:**
  - Traversal uses `max_depth` cap (default 3, max 8)
  - Recursive CTE handles cycles via visited set
  - Cycle is allowed, but result excludes already-visited nodes
- **Recovery:** N/A (expected behavior)
- **Test:** M6.6 (cycle test)

## 4. Security Failures

### 4.1 Permission Denied
- **Severity:** HIGH
- **Detection:** `core.security` permission check fails
- **Impact:** Operation rejected
- **Mitigation:**
  - Permission check BEFORE write attempt
  - Return `PermissionDeniedError` with reason
- **Recovery:**
  - Caller escalates to user/agent
  - No automatic retry
- **Test:** M6.7

### 4.2 Provenance Missing
- **Severity:** MEDIUM
- **Detection:** `KGValidator` requires `provenance` field
- **Impact:** Cannot create node/edge
- **Mitigation:**
  - Validator rejects with `KGValidationError`
  - Caller must supply `MemoryProvenance`
- **Recovery:**
  - Caller adds provenance
- **Test:** M6.7

### 4.3 Soft-Delete Violation
- **Severity:** HIGH
- **Detection:** Attempt to create edge to soft-deleted node
- **Impact:** Edge not created
- **Mitigation:**
  - Validator checks `valid_to IS NULL` on both endpoints
  - Return `NodeNotFoundError` (treats soft-deleted as missing)
- **Recovery:**
  - Caller restores node first, then creates edge
- **Test:** M6.7

## 5. Operational Failures

### 5.1 Schema Migration Failure
- **Severity:** CRITICAL
- **Detection:** Alembic reports failure
- **Impact:** All writes blocked (schema mismatch)
- **Mitigation:**
  - Migration is **additive only** (no column drops, no type changes)
  - Dry-run in CI on every PR
  - Backup before migration (pg_dump)
- **Recovery:**
  - Alembic downgrade to previous revision
  - On success, replay writes from in-memory buffer (if event bus retained)
  - Manual fix if buffer lost
- **Test:** M6.8 (architecture audit verifies no destructive migrations)

### 5.2 Index Corruption
- **Severity:** HIGH
- **Detection:** Slow queries, `pg_stat_user_indexes` shows low scan counts
- **Impact:** Performance degradation
- **Mitigation:**
  - Periodic `REINDEX` (off-hours, scheduled job)
  - Detection via query latency p99 metric
- **Recovery:**
  - `REINDEX INDEX CONCURRENTLY` (online, no lock)
- **Test:** M6.8 (perf benchmark)

### 5.3 EventBus Unavailable
- **Severity:** MEDIUM
- **Detection:** Connection error on event publish
- **Impact:** KG operation succeeds but event not delivered
- **Mitigation:**
  - Local event buffer (in-memory queue, 10K events)
  - Event written to buffer; flush on reconnect
  - If buffer full, drop oldest + alert (events are best-effort telemetry)
- **Recovery:**
  - Buffer drains when EventBus reconnects
  - Lost events logged as warning
- **Test:** M6.7

## 6. Cascading Failures

### 6.1 Cascade Delete
- **Severity:** HIGH
- **Detection:** Node soft-delete with active edges
- **Impact:** Cannot delete node (would orphan edges)
- **Mitigation:**
  - **Cascade is opt-in** (`reason="cascade"` required)
  - All incident edges soft-deleted atomically (single transaction)
  - If any edge fails, transaction rolls back
- **Recovery:**
  - Caller retries with explicit reason
- **Test:** M6.7

### 6.2 Memory Pressure (in-process)
- **Severity:** MEDIUM
- **Detection:** `psutil` memory > 80% of limit
- **Impact:** Degradation, potential OOM
- **Mitigation:**
  - LRU cache cap (1000 entries, configurable)
  - Stream large result sets (don't load all neighbors into memory)
  - Pagination on `get_neighbors` (max 1000 per call)
- **Recovery:**
  - Cache clear on memory pressure
  - Alert on persistent pressure
- **Test:** M6.7 (load test with 100K nodes)

## 7. CR-1907 Dependency

If CR-1907 is approved, the failure matrix is **unchanged** — failure modes are orthogonal to type set size. However, validation failures (3.2) may increase frequency for new types if Pydantic schemas are added without tests.

## 8. Acceptance Criteria

This failure matrix is **frozen** when:
- [ ] Each failure mode has at least 1 test in M6.7 (Failure Injection Tests)
- [ ] Severity classification is consistent with on-call rotation
- [ ] All CRITICAL failures have documented rollback strategy
- [ ] All HIGH failures have documented retry policy
- [ ] Detection mechanisms are observable (metrics or logs)

**Status:** Draft v0.1 — awaiting architect review.
