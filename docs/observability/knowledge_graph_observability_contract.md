# Knowledge Graph Observability Contract (M6)

**Status:** PROPOSED (freeze before M6.0 implementation)
**Date:** 2026-07-03
**Owner:** Memory subsystem
**Related:** knowledge_graph_contract.md, ADR-001-Knowledge-Graph-Storage.md

---

## 1. Observability Principles

> "You cannot improve what you cannot measure." — Peter Drucker

The KG subsystem emits **structured telemetry** for all operations, following these principles:
1. **Every operation emits at least one metric** (count, latency, or error)
2. **Every error emits a structured log with error_code**
3. **Every operation carries a trace_id for correlation**
4. **Events are emitted AFTER successful writes, never before**

## 2. Metrics (Prometheus Format)

All metrics are prefixed `kg_` for Knowledge Graph.

### 2.1 Counters

```
# Operations counter (labels: operation, status)
kg_operations_total{operation="create_node|get_node|update_node|soft_delete_node|create_edge|delete_edge|get_neighbors|find_path|related_entities|merge_nodes|archive", status="success|error|timeout"}

# Cache counters
kg_cache_operations_total{cache="l1|l2", operation="hit|miss|evict|invalidate"}

# Error counters (labels: error_code)
kg_errors_total{error_code="KGValidationError|NodeNotFoundError|EdgeNotFoundError|DuplicateEdgeError|ConcurrentUpdateError|CascadeBlockedError|MaxDepthExceededError|QueryTimeoutError|RepositoryUnavailableError|PermissionDeniedError"}

# Event delivery counter
kg_events_total{event="kg.node.created|kg.node.updated|kg.node.deleted|kg.edge.created|kg.edge.deleted|kg.query.completed|kg.query.failed", delivery="success|buffered|lost"}
```

### 2.2 Histograms (Latency)

```
# Operation latency (labels: operation)
kg_operation_duration_seconds{operation=...}  # buckets: [0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]

# Query depth distribution
kg_query_depth{operation="get_neighbors|find_path"}  # buckets: [1, 2, 3, 4, 5, 6, 7, 8]

# Result set size
kg_query_result_size{operation="get_neighbors|find_path|related_entities"}  # buckets: [1, 10, 100, 1000, 10000]
```

### 2.3 Gauges (Current State)

```
# Active connections to Postgres
kg_db_connections_active

# Cache fill rate
kg_cache_entries{cache="l1|l2"}

# Repository health (1=healthy, 0=unhealthy)
kg_repository_healthy

# Circuit breaker state (0=closed, 1=half_open, 2=open)
kg_circuit_breaker_state{resource="postgres|eventbus"}
```

## 3. Structured Logs (JSON Format)

All logs follow this schema:

```json
{
  "timestamp": "2026-07-03T12:34:56.789Z",
  "level": "INFO|WARN|ERROR|DEBUG",
  "service": "jarvis.memory.kg",
  "trace_id": "uuid-v4",
  "span_id": "uuid-v4",
  "operation": "create_node",
  "duration_ms": 12.5,
  "kg_node_id": "uuid",
  "kg_node_type": "PERSON",
  "kg_edge_type": null,
  "result_count": null,
  "error_code": null,
  "error_message": null,
  "actor": "agent-1234",
  "metadata": {}
}
```

### 3.1 Log Levels

| Level | When | Example |
|---|---|---|
| DEBUG | Detailed diagnostic info (disabled in prod) | SQL query text, full request body |
| INFO | Normal operation success | `create_node` success, `get_neighbors` success |
| WARN | Recoverable issues | Cache miss, retry, soft-delete with active edges |
| ERROR | Operation failures (retryable or not) | All caught exceptions |
| CRITICAL | Service-affecting failures | Postgres down, data corruption |

### 3.2 Required Fields Per Operation

| Operation | Required Log Fields |
|---|---|
| `create_node` | `kg_node_id`, `kg_node_type`, `actor`, `duration_ms` |
| `update_node` | `kg_node_id`, `version`, `actor`, `duration_ms` |
| `soft_delete_node` | `kg_node_id`, `reason`, `actor`, `duration_ms` |
| `create_edge` | `kg_edge_id`, `kg_edge_type`, `source_id`, `target_id`, `actor` |
| `delete_edge` | `kg_edge_id`, `reason`, `actor` |
| `get_neighbors` | `node_id`, `depth`, `direction`, `result_count`, `duration_ms` |
| `find_path` | `source_id`, `target_id`, `result_count` (0 or 1), `duration_ms` |
| `merge_nodes` | `primary_id`, `duplicate_id`, `result_count` |

## 4. Distributed Tracing

### 4.1 Trace Propagation

- All inbound requests MUST carry a `traceparent` header (W3C Trace Context)
- All outbound calls (DB, EventBus) MUST forward the `traceparent` header
- All internal spans MUST share the same `trace_id`
- Span naming: `kg.{operation}.{entity_type}` (e.g., `kg.create_node`)

### 4.2 Spans Emitted

Each KG operation creates a span with these attributes:

| Attribute | Type | Description |
|---|---|---|
| `kg.operation` | string | Operation name |
| `kg.node_id` | string (optional) | Node ID if applicable |
| `kg.edge_id` | string (optional) | Edge ID if applicable |
| `kg.depth` | int (optional) | Query depth if applicable |
| `kg.result_count` | int (optional) | Number of results |
| `kg.cache_hit` | bool | Whether cache was used |
| `kg.db.statement` | string (optional) | SQL query (DEBUG only) |

## 5. Events (EventBus Topics)

All events follow the existing JARVIS event schema (`core.events`):

```python
class EventBase(BaseModel):
    event_id: UUID
    event_type: str  # e.g., "kg.node.created"
    timestamp: datetime
    trace_id: UUID
    actor: str  # agent / user / system
    payload: Dict[str, Any]
```

### 5.1 KG Event Topics (7 topics, frozen)

| Event | Trigger | Payload |
|---|---|---|
| `kg.node.created` | After successful `create_node` | `{node_id, type, label, created_by, confidence}` |
| `kg.node.updated` | After successful `update_node` | `{node_id, old_version, new_version, changes}` |
| `kg.node.deleted` | After successful `soft_delete_node` | `{node_id, reason, cascade_edge_count}` |
| `kg.edge.created` | After successful `create_edge` | `{edge_id, source_id, target_id, type, weight, confidence}` |
| `kg.edge.deleted` | After successful `delete_edge` | `{edge_id, reason}` |
| `kg.query.completed` | After successful query | `{query_type, duration_ms, result_count, depth}` |
| `kg.query.failed` | After query failure | `{query_type, error_code, duration_ms}` |

**Event ordering:** emitted AFTER write commit, never before. No event is emitted for failed operations except `kg.query.failed`.

**Event retention:** 7 days in EventBus, then archived to cold storage.

## 6. Health Check Endpoint

`/health/kg` (called by orchestrator and load balancer):

```json
{
  "status": "healthy | degraded | unhealthy",
  "checks": {
    "repository": {
      "status": "healthy | unhealthy",
      "latency_ms": 5,
      "last_error": null
    },
    "circuit_breaker": {
      "state": "closed | half_open | open",
      "failure_count": 0
    },
    "cache": {
      "l1_size": 8500,
      "l1_hit_rate": 0.82
    }
  },
  "version": "M6.0",
  "timestamp": "2026-07-03T12:34:56Z"
}
```

**Status semantics:**
- `healthy`: all checks pass
- `degraded`: cache miss rate > 50% OR circuit half-open (still serving)
- `unhealthy`: circuit open OR repository unhealthy for >30s

## 7. Alerting Rules (Prometheus AlertManager)

| Alert | Condition | Severity | Response |
|---|---|---|---|
| `KGHighErrorRate` | `sum(rate(kg_errors_total[5m])) > 0.05` | HIGH | Page on-call |
| `KGHighLatencyP99` | `histogram_quantile(0.99, kg_operation_duration_seconds) > 1` | MEDIUM | Investigate |
| `KGRepositoryDown` | `kg_repository_healthy == 0` for 60s | CRITICAL | Page on-call |
| `KGCacheLowHitRate` | `kg_cache_operations_total{operation="hit"} / kg_cache_operations_total{operation=~"hit|miss"} < 0.5` for 30min | LOW | Review cache config |
| `KGQueueBackpressure` | `kg_events_total{delivery="buffered"} > 5000` | MEDIUM | Investigate EventBus |

## 8. CR-1907 Dependency

Observability contract is **unaffected** by CR-1907. New node/edge types do not change metric labels (only label values if new types appear in `kg_node_type`).

## 9. Acceptance Criteria

This contract is **frozen** when:
- [ ] All metrics defined in §2 are emitted by `core/memory/graph.py` (or wherever KG is implemented)
- [ ] All log fields in §3 are populated for every operation
- [ ] All 7 event topics are defined in `core/events/topics.py` and emitted
- [ ] Distributed tracing propagates `traceparent` header
- [ ] Health check endpoint returns JSON per §6
- [ ] All 5 alerting rules are defined in `monitoring/prometheus_alerts.yaml`
- [ ] M6.7 tests verify structured log shape (Pydantic schema)

**Status:** Draft v0.1 — awaiting architect review.
