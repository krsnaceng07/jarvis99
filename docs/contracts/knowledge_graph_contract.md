# Knowledge Graph Component Contract (M6)

**Status:** PROPOSED (freeze before M6.0 implementation)
**Date:** 2026-07-03
**Owner:** Memory subsystem (Phase 19)
**Related:** ADR-001-Knowledge-Graph-Storage.md, Phase 19 spec §16, M6 sub-milestones

---

## 1. Purpose

This contract freezes the **public interface** of the Knowledge Graph subsystem. Anything not in this document is **internal** and may change without notice. Anything in this document is **frozen** and requires a CR to modify.

## 2. Layer Position

Per `docs/architecture/01_ARCHITECTURE_FREEZE.md`:
```
UI  →  API  →  Brain (Orchestrator)  →  Domain (KG)  →  Infrastructure (KGRepository)
```

The Knowledge Graph is in the **Domain** layer. It must not import from API, CLI, Browser, Planner, Agents, Desktop, Voice, Workflow, or any LLM module.

## 3. Public API (Frozen)

### 3.1 DTOs (immutable, schema_version = "1.0")

```python
class KGNode(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    id: UUID
    type: KGNodeType  # 8 frozen types (or 10 if CR-1907 approved)
    label: str  # human-readable
    properties: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    version: int = 1
    created_at: datetime
    updated_at: datetime
    valid_from: datetime  # soft-delete
    valid_to: Optional[datetime] = None  # None = active
    created_by: str  # orchestrator / agent / system
    provenance: MemoryProvenance

class KGEdge(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    id: UUID
    type: KGEdgeType  # 7 frozen types (or 8 if CR-1907 approved)
    source_id: UUID  # KGNode.id
    target_id: UUID  # KGNode.id
    weight: float = Field(ge=0.0, le=1.0, default=1.0)
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    properties: Dict[str, Any] = Field(default_factory=dict)
    version: int = 1
    created_at: datetime
    valid_from: datetime
    valid_to: Optional[datetime] = None
    created_by: str
    provenance: MemoryProvenance
```

### 3.2 Repository Interface (frozen, ABC)

```python
class IKGRepository(ABC):
    @abstractmethod
    async def create_node(self, node: KGNode) -> KGNode: ...

    @abstractmethod
    async def get_node(self, node_id: UUID, include_deleted: bool = False) -> Optional[KGNode]: ...

    @abstractmethod
    async def update_node(self, node: KGNode, expected_version: int) -> KGNode:
        """Optimistic concurrency. Raises ConcurrentUpdateError on version mismatch."""

    @abstractmethod
    async def soft_delete_node(self, node_id: UUID, reason: str) -> None: ...

    @abstractmethod
    async def create_edge(self, edge: KGEdge) -> KGEdge:
        """Idempotent on (source_id, target_id, type)."""

    @abstractmethod
    async def delete_edge(self, edge_id: UUID) -> None: ...

    @abstractmethod
    async def get_neighbors(
        self, node_id: UUID, edge_types: Optional[Set[KGEdgeType]] = None,
        max_depth: int = 1, direction: Literal["out", "in", "both"] = "both"
    ) -> List[KGNode]: ...

    @abstractmethod
    async def find_path(
        self, source_id: UUID, target_id: UUID,
        max_depth: int = 5, edge_types: Optional[Set[KGEdgeType]] = None
    ) -> Optional[List[KGEdge]]: ...

    @abstractmethod
    async def related_entities(
        self, node_id: UUID, min_confidence: float = 0.5
    ) -> List[Tuple[KGNode, float]]: ...
```

### 3.3 Service (thin, frozen)

```python
class KGService:
    def __init__(self, repo: IKGRepository, validator: KGValidator, bus: EventBusInterface): ...

    async def add_node(self, node: KGNode) -> KGNode: ...
    async def add_edge(self, edge: KGEdge) -> KGEdge: ...
    async def find_neighbors(self, ...) -> List[KGNode]: ...
    async def find_path(self, ...) -> Optional[List[KGEdge]]: ...
    async def merge_nodes(self, primary_id: UUID, duplicate_id: UUID) -> KGNode: ...
    async def archive(self, node_id: UUID, reason: str) -> None: ...
```

`KGService` **does not contain business logic**. It delegates to `KGValidator` (input checks), `IKGRepository` (CRUD), and `EventBus` (events).

### 3.4 Formal Interface Structure (10-field, frozen)

Per [docs/governance/compatibility_matrix.md](../governance/compatibility_matrix.md) and Engineering Governance 2.0, every public interface of this contract MUST be specified in the 10-field form below. The corresponding sections of this contract are mapped.

| # | Field | Section in this contract | Frozen? |
|---|---|---|---|
| 1 | **Input** | §3.1, §3.2, §3.3 (DTOs, Repository, Service signatures) | YES |
| 2 | **Output** | §3.1, §3.2, §3.3 (return types) | YES |
| 3 | **Errors** | §5 (9 error types) | YES |
| 4 | **Latency** | §6 (p50/p95/p99 targets) | YES |
| 5 | **Timeout** | §6 (timeout column) | YES |
| 6 | **Idempotency** | §3.1 (DTOs), §3.2 (Repository: `create_node`, `create_edge` are idempotent) | YES |
| 7 | **Thread Safety** | §7 (async, immutable DTOs) | YES |
| 8 | **Concurrency** | §7 (optimistic concurrency, per-row versioning) | YES |
| 9 | **Events** | §8, §13.8 (10 event topics) | YES |
| 10 | **Permissions** | §11 (KG has no authz; Orchestrator owns it — explicit) | YES |

**Rule:** Adding or changing any of the 10 fields requires a CR. This contract is the single source of truth for "what does the KG do?"

---

## 4. Inputs / Outputs

### 4.1 Inputs
- `KGNode` / `KGEdge` from orchestrator (validated by `KGValidator`)
- Query parameters (neighbors, paths) from `MemoryOrchestrator.retrieve()`

### 4.2 Outputs
- `KGNode` / `KGEdge` with version-incremented timestamps
- Query results (lists, optional path)
- Events to `EventBus`: `kg.node.created`, `kg.node.updated`, `kg.node.deleted`, `kg.edge.created`, `kg.edge.deleted`, `kg.query.completed`, `kg.query.failed`

## 5. Errors

| Error | When | Retryable | HTTP code (API layer) |
|---|---|---|---|
| `KGValidationError` | Invalid node/edge data | No | 422 |
| `NodeNotFoundError` | get_node with unknown id | No | 404 |
| `EdgeNotFoundError` | delete_edge with unknown id | No | 404 |
| `DuplicateEdgeError` | Same (source, target, type) exists | No (idempotent return) | 409 |
| `ConcurrentUpdateError` | Optimistic version mismatch | Yes (with retry) | 409 |
| `CascadeBlockedError` | Cannot delete node with active edges | No | 409 |
| `MaxDepthExceededError` | Query depth > 8 | No (caller fix) | 400 |
| `QueryTimeoutError` | Query > 5s | Yes (with smaller scope) | 504 |
| `RepositoryUnavailableError` | Postgres connection lost | Yes (with backoff) | 503 |

## 6. Latency Targets (frozen)

| Operation | Target p50 | Target p95 | Target p99 | Timeout |
|---|---|---|---|---|
| `create_node` | <5ms | <15ms | <50ms | 2s |
| `get_node` | <2ms | <5ms | <20ms | 1s |
| `update_node` | <10ms | <25ms | <75ms | 2s |
| `create_edge` | <5ms | <20ms | <60ms | 2s |
| `get_neighbors (depth=1)` | <10ms | <30ms | <100ms | 2s |
| `get_neighbors (depth=2)` | <30ms | <80ms | <300ms | 5s |
| `get_neighbors (depth=3)` | <100ms | <250ms | <1s | 5s |
| `find_path` | <50ms | <150ms | <500ms | 5s |
| `related_entities` | <20ms | <60ms | <200ms | 3s |

Targets are measured at 100K nodes / 1M edges scale. Tests use 10K nodes / 50K edges for CI speed.

## 7. Thread Safety

- All public methods are **async** and use connection pooling
- Repository is **stateless** (no in-memory mutation between calls)
- `KGNode` / `KGEdge` DTOs are **immutable** (Pydantic frozen model)
- Optimistic concurrency: caller passes `expected_version`, repo raises `ConcurrentUpdateError` on mismatch
- No global locks; per-row versioning

## 8. Events Emitted

```python
# On success, AFTER write
kg.node.created    # {node_id, type, created_by, timestamp}
kg.node.updated    # {node_id, version, changes}
kg.node.deleted    # {node_id, reason, timestamp}
kg.edge.created    # {edge_id, source_id, target_id, type}
kg.edge.deleted    # {edge_id, reason}
kg.query.completed # {query_type, latency_ms, result_count}
kg.query.failed    # {query_type, error_code, error_message}
```

**Event ordering:** emitted AFTER successful write, never before.

## 9. Ownership

- **Component owner:** Memory subsystem lead
- **Code reviewer:** Architect + 1 senior engineer
- **On-call:** Memory rotation
- **Documentation:** This contract, ADR-001, failure matrix, performance budget, observability contract

## 10. Dependencies (Allowed)

- `core.memory.dto` (DTOs, frozen spec §16.5/§16.6)
- `core.memory.validator` (KGValidator)
- `core.interfaces.EventBusInterface`
- `core.config.MemoryConfig` (memory config)
- `sqlalchemy.ext.asyncio` (DB driver)
- `psycopg` / `asyncpg` (Postgres async)
- `uuid`, `datetime`, `typing`, `enum`, `dataclasses` (stdlib)

## 11. Dependencies (Forbidden)

- ❌ `api/*`
- ❌ `cli/*`
- ❌ `core.brain` / `core.orchestrator`
- ❌ `core.retrieval` / `core.scoring` / `core.retention` (other memory engines)
- ❌ `core.browser` / `core.desktop` / `core.voice` / `core.vision`
- ❌ `core.llm` / `core.embedding` (no LLM logic in KG)
- ❌ `core.planner` / `core.agents` / `core.workflow`

## 13. The 10 Frozen Sub-Contracts

The Knowledge Graph is decomposed into **10 sub-contracts**. Each is independently frozen and CR-controlled. Together they define *what* M6 must deliver.

### 13.1 KG Node Identity (frozen)

- **Identity primitive:** `UUID v4` generated by `uuid.uuid4()`. Never sequential. Never derived from content.
- **Content addressing:** `node.content_hash` (SHA-256 of canonicalized label + properties) is *additional*, not the primary id.
- **Idempotency:** If a node with the same `(type, content_hash, valid_from)` already exists, `create_node` returns the existing one — never duplicates.
- **Cross-graph reference:** Edges reference nodes by `UUID`, never by label or hash.
- **Immutability:** Once `id` is set, it never changes for the lifetime of the node (even across merges — see 13.5).
- **Origin:** `created_by` field records *which* orchestrator/agent/system created the node.

### 13.2 KG Edge Identity (frozen)

- **Identity primitive:** `UUID v4`.
- **Direction:** Edges are **directed** by default. An undirected relationship is modeled as two opposing edges with the same type.
- **Multiplicity:** The pair `(source_id, target_id, type)` is **unique per active edge**. A second create returns the existing edge (idempotent).
- **Properties:** `weight ∈ [0.0, 1.0]`, `confidence ∈ [0.0, 1.0]`, `properties: Dict[str, Any]`. The keys in `properties` are typed via the edge's `type` definition (a future schema table).
- **Self-loops:** Permitted only for `KGEdgeType.RELATED_TO`. Forbidden for all other types.
- **No hyperedges:** Only binary edges. N-ary relationships are modeled as an intermediate node.

### 13.3 Traversal Rules (frozen)

- **Default depth limit:** 3. Maximum permitted: 8 (raises `MaxDepthExceededError`).
- **Direction:** `Literal["out", "in", "both"]`. Default: `"both"`.
- **Cycle prevention:** Traversal engine MUST maintain a visited-set keyed by `(node_id, depth_reached)` and never revisit the same node at the same or greater depth.
- **Path uniqueness:** `find_path` returns the **shortest path** by hop count. Ties broken by `weight DESC, confidence DESC`.
- **Edge-type filtering:** Traversal MUST honor `edge_types: Optional[Set[KGEdgeType]]` filter. If `None`, all edge types are allowed.
- **Soft-deleted nodes/edges:** Never traversed. `valid_to IS NOT NULL` excludes them from results.
- **Result ordering:** `get_neighbors` returns nodes by `confidence DESC, id ASC`. Stable across calls.

### 13.4 Inference Rules (frozen)

- **Inference is read-only.** It MUST NOT mutate the graph.
- **Engine boundary:** `InferenceEngine` is a separate component from `KGService` and `IKGRepository`. It calls `IKGRepository.find_path` / `get_neighbors` and applies rules.
- **Allowed inferences (v1.0):**
  - Transitive closure: if `A → KNOWS → B` and `B → KNOWS → C` exist, infer `A → KNOWS → C` with `confidence = min(conf_A_B, conf_B_C)`. ONLY if the edge-type definition permits transitivity.
  - Symmetric inference: if `A → RELATED_TO → B` exists, infer `B → RELATED_TO → A` (only `RELATED_TO` is symmetric).
- **Forbidden inferences (v1.0):**
  - No LLM-based inference.
  - No probabilistic reasoning beyond min/max aggregation.
  - No automatic edge creation. Inferences are returned by the engine, not persisted.
- **Opt-in:** Callers must explicitly request inference via `KGQuery(apply_inference=True)`. Default is `False`.

### 13.5 Merge Rules (frozen)

- **Trigger:** Manual via `KGService.merge_nodes(primary_id, duplicate_id, reason)`. Never automatic.
- **Pre-conditions:**
  - Both nodes must exist and be active (`valid_to IS NULL`).
  - Both nodes MUST be of the same `KGNodeType`.
- **Algorithm:**
  1. Choose the node with the higher `confidence` as `primary`. If tied, the older `created_at` wins.
  2. Re-point all edges from `duplicate` to `primary` (update `source_id` or `target_id`).
  3. Merge `properties`: deep-merge, primary wins on conflict.
  4. Soft-delete `duplicate` with `valid_to = now()` and `properties["merged_into"] = primary_id`.
  5. Emit `kg.node.merged` event with both ids and reason.
- **Idempotency:** If `duplicate_id` is already merged (i.e. `properties["merged_into"]` is set), return `primary` without re-merge.
- **No silent merges:** Every merge MUST emit an event. Auditable.

### 13.6 Conflict Resolution (frozen)

- **Conflict types:**
  - **Property conflict:** Two updates to the same node set different `properties[k]`.
  - **Edge conflict:** Two creates for the same `(source_id, target_id, type)` with different `weight` or `properties`.
  - **Version conflict:** Optimistic concurrency version mismatch.
- **Resolution policy:**
  - **Property conflict:** Last-write-wins (LWW) by `updated_at` timestamp, with the losing value stored in `properties["conflict_history"]` (a list, capped at 10 entries).
  - **Edge conflict:** First-create wins. Subsequent creates with different `weight` update the existing edge (idempotent return) and emit `kg.edge.updated`.
  - **Version conflict:** Caller's `expected_version` mismatch → raise `ConcurrentUpdateError`. Caller may retry.
- **No silent overwrites:** All conflicts emit an event (`kg.conflict.detected`) carrying both old and new values.
- **No automatic resolution for property conflicts:** LWW is the *default*; the orchestrator can opt out by registering a custom resolver (post-v1.0).

### 13.7 Graph Versioning (frozen)

- **Per-node / per-edge version:** Integer, starts at 1, increments on every update.
- **Optimistic concurrency:** All updates require `expected_version`. Mismatch raises `ConcurrentUpdateError` (HTTP 409).
- **Graph-level version (optional v1.0):** A monotonically increasing `graph_version: int` is recorded in a singleton row. Incremented on any node/edge create, update, soft-delete, or merge. Used for snapshot/cache invalidation.
- **No branching:** The graph is a single linear history. No fork/merge at the graph level (per-node merging only, see 13.5).
- **Soft-delete versioning:** `valid_from` / `valid_to` are bitemporal. A node has a `valid_time` axis independent of the `version` integer.

### 13.8 Graph Events (frozen)

- **Event topics (canonical names in `core/events/topics.py`):**
  - `kg.node.created`     → `{node_id, type, created_by, timestamp}`
  - `kg.node.updated`     → `{node_id, version, changes: Dict}`
  - `kg.node.deleted`     → `{node_id, reason, timestamp}`
  - `kg.node.merged`      → `{primary_id, duplicate_id, reason}`
  - `kg.edge.created`     → `{edge_id, source_id, target_id, type}`
  - `kg.edge.updated`     → `{edge_id, version, changes: Dict}`
  - `kg.edge.deleted`     → `{edge_id, reason}`
  - `kg.conflict.detected`→ `{entity, entity_id, old_value, new_value, resolution}`
  - `kg.query.completed`  → `{query_type, latency_ms, result_count}`
  - `kg.query.failed`     → `{query_type, error_code, error_message}`
- **Ordering:** All events emitted **after** successful write. Never before.
- **Delivery:** At-least-once via `EventBusInterface`. Consumers must be idempotent.
- **Payload schema version:** Each payload carries `schema_version: Literal["1.0"]`.
- **No PII in events:** Events contain ids and types only, never raw `properties` content (PII risk).

### 13.9 Graph Indexes (frozen)

Required Postgres indexes for performance budget (see `docs/performance/knowledge_graph_performance_budget.md`):

- `kg_nodes (id) PRIMARY KEY`
- `kg_nodes (type, valid_to)` — for type-filtered active-node queries
- `kg_nodes (content_hash) UNIQUE WHERE valid_to IS NULL` — for content-addressed dedup
- `kg_nodes USING GIN (properties jsonb_path_ops)` — for property search
- `kg_edges (id) PRIMARY KEY`
- `kg_edges (source_id, target_id, type) UNIQUE WHERE valid_to IS NULL` — for edge dedup
- `kg_edges (target_id)` — for inbound neighbor queries
- `kg_edges USING GIN (properties jsonb_path_ops)` — for property search
- `kg_nodes_graph_version (graph_version DESC)` — for snapshot retrieval
- `kg_audit (entity_type, entity_id, version)` — for conflict history queries

**Index maintenance:** Indexes are created in M6.0 schema migration. Dropped only via CR.

### 13.10 Graph Persistence (frozen)

- **Backend:** PostgreSQL via `asyncpg` (raw SQL) or `SQLAlchemy 2.0 async`. The repository implementation must choose one and document the choice in its file header.
- **Schema location:** Migrations live in `db/migrations/versions/`. New migrations append a sequential prefix (e.g. `m6_001_create_kg_nodes.sql`).
- **Connection pooling:** Per-process pool, default min=2, max=10. Configurable via `core.config.MemoryConfig.kg_pool_size`.
- **Transactions:** All multi-row operations (merge, cascade-delete) wrapped in a single transaction. Failure rolls back the entire operation.
- **No in-memory fallback:** Repository MUST raise `RepositoryUnavailableError` if Postgres is unreachable. No silent in-memory substitute.
- **Backup:** Daily `pg_dump` of the `kg_*` tables. Retention: 30 days. (Operational concern, not enforced in code.)
- **Migration ordering:** Forward migrations are append-only. Backward migrations require a CR.

---

## 14. Acceptance Criteria

This contract is **frozen** when:
- [ ] All public DTOs are defined with `schema_version: Literal["1.0"]`
- [ ] `IKGRepository` is defined as ABC with all 9 abstract methods
- [ ] Error hierarchy is implemented in `core/memory/errors.py`
- [ ] All 9 latency targets are measured in M6.8 architecture audit
- [ ] All 11 forbidden dependency rules are tested by `audit/architecture_audit.py`
- [ ] All 10 event topics are defined in `core/events/topics.py`
- [ ] All 10 sub-contracts (§13.1 – §13.10) have at least one test each
- [ ] All 9 required Postgres indexes are created in the M6.0 migration
- [ ] CR-1907 resolution is recorded (or types confirmed as spec §16.5/§16.6)

**Status:** Draft v0.2 — extended with 10 sub-contracts (2026-07-03), awaiting architect review.
