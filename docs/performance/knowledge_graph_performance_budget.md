# Knowledge Graph Performance Budget (M6)

**Status:** PROPOSED (freeze before M6.0 implementation)
**Date:** 2026-07-03
**Owner:** Memory subsystem
**Related:** knowledge_graph_contract.md, ADR-001-Knowledge-Graph-Storage.md
**Frozen:** YES (requires CR to modify)

---

## 1. Scale Targets

| Metric | Phase 19 (M6 launch) | Phase 20+ target | Stretch |
|---|---|---|---|
| Total nodes | 100,000 | 1,000,000 | 10,000,000 |
| Total edges | 1,000,000 | 10,000,000 | 100,000,000 |
| Concurrent readers | 50 | 500 | 5,000 |
| Concurrent writers | 10 | 100 | 1,000 |
| Read QPS (steady state) | 100 | 1,000 | 10,000 |
| Write QPS (steady state) | 20 | 200 | 1,000 |

**Test scale (CI):** 10,000 nodes, 50,000 edges. Proves the implementation; production scale extrapolated.

## 2. Latency Budget (per Operation)

Frozen at these p50/p95/p99 targets. Tests in `tests/test_memory_kg_performance.py` must verify these.

| Operation | p50 | p95 | p99 | Timeout |
|---|---|---|---|---|
| `create_node` | <5ms | <15ms | <50ms | 2s |
| `get_node` | <2ms | <5ms | <20ms | 1s |
| `update_node` (with version check) | <10ms | <25ms | <75ms | 2s |
| `soft_delete_node` | <10ms | <25ms | <75ms | 2s |
| `create_edge` | <5ms | <20ms | <60ms | 2s |
| `delete_edge` | <5ms | <15ms | <50ms | 2s |
| `get_neighbors (depth=1)` | <10ms | <30ms | <100ms | 2s |
| `get_neighbors (depth=2)` | <30ms | <80ms | <300ms | 5s |
| `get_neighbors (depth=3)` | <100ms | <250ms | <1s | 5s |
| `find_path` | <50ms | <150ms | <500ms | 5s |
| `related_entities` | <20ms | <60ms | <200ms | 3s |
| `merge_nodes` | <100ms | <300ms | <1s | 10s |
| `archive` (single node + cascade) | <50ms | <200ms | <500ms | 10s |

## 3. Throughput Targets

| Operation | Min QPS | Target QPS | Stretch QPS |
|---|---|---|---|
| `create_node` (batched 100) | 200 | 1,000 | 5,000 |
| `get_node` (cache miss) | 500 | 2,000 | 10,000 |
| `get_neighbors (depth=1)` | 100 | 500 | 2,000 |
| `find_path` (avg depth 3) | 20 | 100 | 500 |

## 4. Memory Budget

| Item | Limit (in-process) | Per-call | Notes |
|---|---|---|---|
| In-process LRU cache (read) | 50MB | — | 10,000 entries avg 5KB each |
| Per-call result buffer | 50MB | 50MB | for `get_neighbors` with 10K results |
| Connection pool | 10MB | — | 20 connections × 500KB |
| Recursive CTE intermediate | 100MB | 100MB | Postgres work_mem for query |

**Hard cap:** 250MB per request (enforced in M6.7 tests).

## 5. Database Sizing (Postgres)

| Table | Initial Size (1K nodes) | 100K nodes | Indexes |
|---|---|---|---|
| `kg_nodes` | 100KB | 50MB | PK (id), idx (type, valid_to) |
| `kg_edges` | 1MB | 500MB | PK (id), idx (source_id, type), idx (target_id, type), idx (type, valid_to) |
| `kg_audit_log` | 10MB | 1GB | PK (id, ts), idx (node_id, ts) |

Indexes add ~30% to table size. Total estimated at 100K nodes: 700MB.

## 6. Concurrency Limits

| Resource | Limit | Reason |
|---|---|---|
| Max concurrent connections | 20 | Connection pool size |
| Max active transactions | 20 | 1:1 with connections |
| Max query depth | 8 (configurable) | Prevent runaway recursion |
| Max result set size | 10,000 rows | Memory cap |
| Max audit log retention | 90 days | Compliance + storage cost |

## 7. Network Budget (per Request)

| Metric | Budget | Notes |
|---|---|---|
| Request size (typical) | <2KB | DTO JSON |
| Response size (typical) | <10KB | Result list |
| Response size (max) | <1MB | Capped via pagination |
| Latency p99 (network) | <100ms | Service-to-service within cluster |

## 8. Cache Strategy

| Cache | Size | TTL | Hit rate target |
|---|---|---|---|
| L1 in-process LRU (read) | 10,000 entries | 5 min | 80% |
| L2 Redis (read) | 100,000 entries | 1 hour | 95% (combined) |
| L3 Postgres material view | N/A | N/A | N/A for M6 (Phase 20+) |

**Cache invalidation:** on `kg.node.updated` or `kg.node.deleted`, evict from L1 + publish invalidation to L2.

## 9. CR-1907 Dependency

Performance budget is **unaffected** by CR-1907. Type set size (8 vs 10) does not change query latency materially (it changes selectivity, which is bounded by index design).

## 10. Performance Test Plan (M6.8)

Required tests in `tests/test_memory_kg_performance.py`:

```python
def test_create_node_latency_p95(benchmark_setup):
    # 10,000 nodes, measure p95 < 15ms

def test_get_neighbors_depth_2_latency_p95(benchmark_setup):
    # 10,000 nodes, 50,000 edges, p95 < 80ms

def test_throughput_create_node_batch(benchmark_setup):
    # batch of 100, ≥1000 QPS

def test_memory_cap_under_load(benchmark_setup):
    # load 100K nodes, in-process memory < 250MB
```

## 11. SLO (Service Level Objective)

For Phase 19 M6 launch:
- **Availability:** 99.5% (single-region, no HA yet — Phase 20+ adds HA)
- **Latency p99:** ≤ 500ms for `get_neighbors (depth=2)` (under 100K nodes)
- **Error rate:** < 0.5% (excluding client errors 4xx)

SLO breaches trigger alerts. SLO revision requires CR.

## 12. Acceptance Criteria

This budget is **frozen** when:
- [ ] All latency targets are verified by automated tests (M6.8)
- [ ] Throughput targets are validated under load test (M6.8)
- [ ] Memory caps are enforced in tests (M6.7)
- [ ] SLO is documented and alertable
- [ ] CI fails if any regression > 20% from baseline

**Status:** Draft v0.1 — awaiting architect review.
