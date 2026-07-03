# PHASE 19 — REAL MEMORY ARCHITECTURE SPECIFICATION

## Status

STATUS: FROZEN
VERSION: 1.0
DATE: 2026-06-30
FREEZE_DATE: 2026-06-30
AUTHOR: Architecture Team
IMPLEMENTATION_PLAN:
docs/81_PHASE_19_IMPLEMENTATION_PLAN.md

SCOPE: Upgrade the memory subsystem from basic CRUD to intelligent memory management with working memory, scoring, promotion, forgetting, and retrieval ranking.

---

## 1. OBJECTIVE

Transform the memory subsystem from a flat store-and-retrieve model into a tiered, scored, and lifecycle-managed memory architecture that mirrors how humans organize information: working memory (immediate), session memory (recent), long-term memory (persistent), semantic memory (embedded), and knowledge graph (relational).

**What exists today (Phase 18 baseline):**
- `MemoryService` — basic CRUD with dedup (SHA256 content hash)
- `PostgresMemoryRepository` — relational storage for chunks and sources
- `PostgresVectorRepository` — pgvector HNSW cosine similarity search
- `PostgresKnowledgeGraphRepository` — BFS graph traversal
- `RetrievalEngine` — keyword + vector hybrid search with RRF fusion
- `MemoryIntelligenceService` — personal memory auto-classification, version conflict resolution
- `PersonalMemoryRepository` — versioned user facts with tiered retrieval
- `MemoryIndexer` — event-driven vector + graph indexing
- 15 memory tests passing

**What this phase adds:**
- Working Memory tier (L1) — fast in-process LRU cache for hot context
- Session Memory tier (L2) — scoped to conversation, auto-promotes to long-term
- Memory Scoring model — weighted composite score for ranking
- Promotion Policy — rules for moving memories between tiers
- Forgetting Policy — TTL, decay, archive, and cascade delete
- Retrieval Ranking — recency, frequency, confidence, trust-weighted scoring
- Reflection — memory update after execution outcomes
- Memory API routes — REST endpoints for memory CRUD
- Memory CLI — command-line interface for memory operations

**Out of scope:**
- Redis working memory (L1 uses in-process LRU; Redis is a future CR)
- Real embedding provider (MockEmbeddingGenerator suffices; OpenAI/Ollama is a future CR)
- Cross-encoder re-ranking (RRF fusion is sufficient for v1)
- S3/file-based archive pipeline (archive is logical, not physical)

---

## 2. ARCHITECTURE

### 2.1 Memory Tier Model

```
┌─────────────────────────────────────────────────────────────┐
│                    MEMORY TIERS                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  L0: Identity      │ Immutable user facts, system config    │
│      (Repository)  │ Never forget, never decay              │
│                    │ Access: direct lookup by key            │
│                                                              │
│  L1: Working       │ Fast LRU cache, per-session hot context │
│      (InProcess)   │ TTL: 10 minutes, max 50 items         │
│                    │ Auto-evicts on LRU                      │
│                                                              │
│  L2: Conversation  │ Conversation-scoped, auto-promotes     │
│      (Repository)  │ TTL: 24 hours, max 200 items           │
│                    │ Promotion trigger: access_count >= 3    │
│                                                              │
│  L3: Long-Term     │ Persistent relational storage           │
│      (Repository)  │ TTL: 30 days, scored by importance     │
│                    │ Promotion trigger: score >= 0.7         │
│                                                              │
│  KG: Knowledge     │ Entity-relationship graph               │
│      (Graph)       │ Nodes + edges, BFS traversal            │
│                    │ Promotion trigger: entity extraction    │
│                                                              │
│  VECTOR (repr.)    │ Vector embeddings for similarity search │
│      (VectorStore) │ Applied to any tier, not a tier itself  │
│                    │ Auto-generated when chunk reaches L3    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Dependency Direction

```
API Routes → CLI
    ↓
MemoryOrchestrator (NEW)
    ↓
┌────────────────────────────────────────────────┐
│ MemoryService    │ RetentionEngine │ ScoringEngine │
│ (CRUD)           │ (Promotion/     │ (Score calc)  │
│                  │  Forgetting)    │               │
└────────────────────────────────────────────────┘
    ↓               ↓                ↓
Repository │ VectorStore │ KnowledgeGraph
    ↓
PostgreSQL / SQLite
```

**Invariants:**
- `MemoryOrchestrator` is the sole entry point for all memory operations
- `MemoryService` retains CRUD responsibility only — no business logic
- `RetentionEngine` owns promotion and forgetting decisions
- `ScoringEngine` owns score calculation — pure function, no IO
- Routes and CLI never call repositories directly

### 2.3 Memory Entity Lifecycle

```
                    ┌──────────────┐
                    │   CREATED    │
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  INDEXING    │ (vector + graph)
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
              ┌────►│   ACTIVE     │◄─────┐
              │     └──────┬───────┘      │
              │            │              │
    access_count >= 3      │       score >= 0.7
    (auto-promote)         │       (score-based)
              │            │              │
              │     ┌──────▼───────┐      │
              │     │ PROMOTED     │──────┘
              │     └──────┬───────┘
              │            │
              │     ┌──────▼───────┐
              │     │  DECAYING    │ (freshness < threshold)
              │     └──────┬───────┘
              │            │
              │     ┌──────▼───────┐
              └─────┤  ARCHIVED    │ (TTL expired, or manual)
                    └──────┬───────┘
                           │
                    ┌──────▼───────┐
                    │  FORGOTTEN   │ (cascade delete)
                    └──────────────┘
```

### 2.4 Event Topics (FROZEN CONTRACT)

Memory event topics are an immutable contract. Never rename after freeze.

| Topic | When | Payload |
|-------|------|---------|
| `memory.created` | New memory stored | `{memory_id, owner_id, tier, memory_type, score}` |
| `memory.updated` | Memory content or metadata changed | `{memory_id, fields_changed}` |
| `memory.promoted` | Tier upgrade | `{memory_id, old_tier, new_tier, score}` |
| `memory.archived` | Moved to archive (logical) | `{memory_id, tier, archive_reason}` |
| `memory.deleted` | Soft-deleted (TTL or manual) | `{memory_id, tier, forget_reason}` |
| `memory.retrieved` | Read/retrieved in recall | `{memory_id, tier, access_count, query}` |
| `memory.reflected` | Post-execution reflection applied | `{memory_id, outcome, confidence_delta}` |
| `memory.indexed` | Vector + graph indexing complete | `{memory_id, vector_id, graph_node_id}` |

---

## 3. MEMORY SCORING

### 3.1 Scoring Formula (FROZEN CONTRACT)

The scoring formula is an immutable contract. Weights are configurable; the formula structure is not.

```
FinalScore = Recency + SemanticSimilarity + Confidence + Importance + Frequency + Trust + UserPin
```

**Component definitions (frozen):**

| Component | Definition | Range |
|-----------|-----------|-------|
| Recency | Exponential decay: `e^(-lambda * delta_hours)` | 0.0 – 1.0 |
| SemanticSimilarity | Cosine similarity of embedding vectors | 0.0 – 1.0 |
| Confidence | Memory accuracy confidence at creation/reflection | 0.0 – 1.0 |
| Importance | Importance assigned during creation | 0.0 – 1.0 |
| Frequency | Log-normalized access count: `ln(1 + access_count) / ln(1 + max_access_count)` | 0.0 – 1.0 |
| Trust | Source trust level (see §3.3) | 0.0 – 1.0 |
| UserPin | Binary boost: `1.0` if user-pinned, `0.0` otherwise | 0 or 1 |

**Weight application (configurable):**

```python
FinalScore = (
    w_recency * Recency +
    w_semantic * SemanticSimilarity +
    w_confidence * Confidence +
    w_importance * Importance +
    w_frequency * Frequency +
    w_trust * Trust +
    w_pin * UserPin
)
```

Default weights live in `MemoryScoringConfig` (§8.4). The formula structure above is frozen; weights may be tuned without a CR.

### 3.2 Default Weights

| Weight | Default | Meaning |
|--------|---------|---------|
| `w_recency` | 0.25 | How recently the memory was accessed |
| `w_semantic` | 0.20 | Cosine similarity of embeddings |
| `w_confidence` | 0.20 | Confidence in the memory's accuracy |
| `w_importance` | 0.15 | Importance assigned during creation |
| `w_frequency` | 0.10 | How often the memory is accessed |
| `w_trust` | 0.05 | Trust level of the source |
| `w_pin` | 1.00 | Binary user-pin boost |
| `lambda` | 0.05 | Decay rate (half-life ≈ 14 hours) |

### 3.3 Trust Levels

| Level | Value | Source |
|-------|-------|--------|
| SYSTEM | 1.0 | Kernel, system config |
| USER_EXPLICIT | 0.9 | User-stated facts |
| USER_IMPLICIT | 0.7 | Inferred from user behavior |
| LEARNED | 0.5 | Scraped/extracted from web |
| INFERRED | 0.3 | Derived from other memories |

---

## 4. PROMOTION POLICY

### 4.1 Memory Promotion Tiers (FROZEN)

Promotion follows a strict directional flow. Vector indexing is NOT a tier — it is a **representation** applied to any tier.

```
Working (L1, in-process LRU)
    ↓
Conversation (L2, session-scoped)
    ↓
Long Term (L3, persistent relational)
    ↓
Knowledge Graph (KG, entity-relationship)
```

**Clarification:** Vector embeddings are a search representation, not a memory tier. Any tier may have an associated vector embedding. Vector indexing is triggered automatically when a memory reaches L3, but it does not constitute a promotion.

### 4.2 Promotion Triggers

| Trigger | From → To | Condition |
|---------|-----------|-----------|
| Hot Access | L1 → L2 | access_count >= 3 within TTL |
| Persist Intent | L2 → L3 | score >= 0.7 AND access_count >= 2 |
| Knowledge Link | L3 → KG | Chunk has entity extraction results |

### 4.3 Promotion Rules

1. **L1 → L2:** Working memory item accessed 3+ times in 10 minutes → copy to session memory
2. **L2 → L3:** Session memory item with score >= 0.7 and accessed 2+ times → persist to long-term
3. **L3 → KG:** Long-term chunk with extracted entities → create graph nodes + edges
4. **Vector Indexing (not promotion):** When a chunk reaches L3, an embedding is automatically generated and stored in the vector index. This is a representation step, not a tier change.

### 4.4 Promotion Safety

- Promotions are idempotent (re-promoting the same memory is a no-op)
- Promotions emit events AFTER both source and target tier writes succeed
- Failed promotions leave the source tier unchanged (atomic)
- Maximum 1 promotion per memory per 60 seconds (throttle)

---

## 5. FORGETTING POLICY

### 5.1 Forgetting Triggers

| Trigger | Tier | Condition |
|---------|------|-----------|
| TTL Expiry | L1 | age > 10 minutes |
| TTL Expiry | L2 | age > 24 hours |
| Score Decay | L3 | score < 0.2 |
| Manual Forget | Any | User/agent explicit request |
| Cascade Delete | Any | Source entity deleted |
| GDPR Request | Any | User data deletion request |

### 5.2 Forgetting Rules

1. **L1 TTL:** Items older than 10 minutes are evicted from working memory (in-memory only, no DB write)
2. **L2 TTL:** Items older than 24 hours are either promoted to L3 (if score >= 0.7) or deleted
3. **L3 Decay:** Items with score < 0.2 are moved to ARCHIVED tier (logical flag, not physical delete)
4. **Archive Retention:** Archived items are retained for 30 days, then hard-deleted
5. **Cascade Delete:** When a source entity is deleted, all dependent memories are soft-deleted
6. **GDPR:** Full user-context deletion across all tiers, vector store, and knowledge graph

### 5.3 Archive Format

Archived memories are stored in the same `memory_chunks` table with `is_archived=True` flag. They are excluded from normal retrieval queries but retained for audit and potential restoration.

---

## 6. RETRIEVAL PIPELINE

### 6.1 Enhanced Retrieval Flow (FROZEN ORDER)

The retrieval pipeline order is an immutable contract. Steps must execute in this exact sequence.

```
┌──────────────────────────────────────────────────────────┐
│                   RETRIEVAL PIPELINE                       │
│                   (frozen order)                           │
├──────────────────────────────────────────────────────────┤
│                                                           │
│  Step 1: Query                                            │
│    └── Receive raw query string                           │
│                                                           │
│  Step 2: Intent Analysis                                  │
│    └── Extract keywords, intent, tier preference          │
│                                                           │
│  Step 3: Permission Filter (BEFORE candidate generation)  │
│    └── Remove unauthorized memories by visibility/tier    │
│                                                           │
│  Step 4: Candidate Generation                             │
│    ├── L0: Identity direct lookup                         │
│    ├── L1: Working memory LRU cache                       │
│    ├── L2: Conversation-scoped retrieval                  │
│    └── L3: Long-term keyword search (ILIKE)               │
│                                                           │
│  Step 5: Vector Search                                    │
│    └── Cosine similarity against embeddings               │
│                                                           │
│  Step 6: Knowledge Graph Expansion                        │
│    └── BFS from root nodes, max_depth configurable        │
│                                                           │
│  Step 7: Hybrid Merge                                     │
│    └── RRF fusion of keyword + vector + graph results     │
│                                                           │
│  Step 8: Scoring                                          │
│    └── Composite score (§3.1 frozen formula)              │
│                                                           │
│  Step 9: Ranking                                          │
│    ├── Score-based primary sort                           │
│    ├── Recency tiebreaker                                 │
│    └── Source trust tiebreaker                            │
│                                                           │
│  Step 10: Context Compression                             │
│    └── Token budget enforcement + chunk truncation        │
│                                                           │
│  Step 11: Planner                                         │
│    └── Return ranked results to caller                    │
│                                                           │
└──────────────────────────────────────────────────────────┘
```

### 6.2 Retrieval API DTOs

```python
class MemoryRecallRequest(BaseModel):
    query: str
    max_chunks: int = 50
    max_tokens: int = 2000
    min_score: float = 0.0
    tier_filter: Optional[List[MemoryTier]] = None
    graph_depth: int = 0
    graph_root_node_id: Optional[UUID] = None
    include_archived: bool = False

class MemoryRecallResponse(BaseModel):
    chunks: List[MemoryChunkDTO]
    graph_nodes: List[MemoryNodeDTO]
    total_tokens: int
    scores: List[MemoryScoreDTO]
    metadata: RecallMetadata

class MemoryScoreDTO(BaseModel):
    chunk_id: UUID
    score: float
    recency: float
    frequency: float
    confidence: float
    importance: float
    trust: float
    tier: MemoryTier

class RecallMetadata(BaseModel):
    query_time_ms: float
    chunks_searched: int
    tiers_hit: List[MemoryTier]
    budget_used: int
    budget_remaining: int
```

---

## 7. REFLECTION

### 7.1 Reflection Boundary (FROZEN)

Reflection is scoped exclusively to memory updates. It must NOT modify:

- Skills (Phase 18 frozen)
- Planner decisions
- Workflows or orchestrators
- Runtime configuration
- Other agents' state

Self-improvement through reflection on code/skills/planner is deferred to Phase 23+.

### 7.2 Reflection Contract

After each tool execution or agent action, the system may update related memories based on outcomes:

```python
class ReflectionRequest(BaseModel):
    source_chunk_id: UUID
    outcome: ExecutionOutcome  # success, failure, partial
    confidence_delta: float    # -1.0 to +1.0
    notes: Optional[str] = None

class ExecutionOutcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    TIMEOUT = "timeout"
```

### 7.2 Reflection Rules

1. **Success:** Increase confidence by `confidence_delta` (max 1.0)
2. **Failure:** Decrease confidence by `confidence_delta` (min 0.0)
3. **Partial:** Small confidence adjustment based on delta
4. **Timeout:** Decrease importance, increase recency (still relevant)
5. Reflection emits `memory.reflection.completed` event
6. Confidence changes trigger re-scoring

---

## 8. COMPONENT SPECIFICATIONS

### 8.1 ScoringEngine (NEW)

**File:** `core/memory/scoring.py`

**Responsibility:** Pure-function score calculation. No IO.

```python
class ScoringEngine:
    def __init__(self, config: MemoryScoringConfig): ...
    
    def calculate_score(
        self,
        chunk: MemoryChunkDTO,
        access_count: int,
        last_accessed: datetime,
        source_trust: float,
        now: datetime,
    ) -> MemoryScoreDTO:
        """Calculate composite score for a memory chunk."""
        ...
    
    def rank_chunks(
        self,
        chunks: List[MemoryChunkDTO],
        access_counts: Dict[UUID, int],
        source_trusts: Dict[UUID, float],
        now: datetime,
    ) -> List[MemoryScoreDTO]:
        """Rank multiple chunks by composite score."""
        ...
```

**Invariants:**
- Pure function, no side effects
- Deterministic (same inputs → same output)
- Configurable weights via `MemoryScoringConfig`

### 8.2 RetentionEngine (NEW)

**File:** `core/memory/retention.py`

**Responsibility:** Promotion and forgetting decisions. Coordinates with repositories.

```python
class RetentionEngine:
    def __init__(
        self,
        memory_repo: IMemoryRepository,
        scoring_engine: ScoringEngine,
        config: MemoryRetentionConfig,
    ): ...
    
    async def evaluate_promotions(
        self,
        session_id: UUID,
        now: datetime,
    ) -> List[PromotionAction]:
        """Evaluate and execute pending promotions for a session."""
        ...
    
    async def evaluate_forgetting(
        self,
        now: datetime,
    ) -> List[ForgettingAction]:
        """Evaluate and execute pending forgetting across all tiers."""
        ...
    
    async def archive_chunk(
        self,
        chunk_id: UUID,
        reason: str,
    ) -> bool:
        """Move a chunk to archived tier."""
        ...
    
    async def cascade_delete(
        self,
        source_id: UUID,
        reason: str,
    ) -> int:
        """Delete all chunks from a source entity."""
        ...
```

**Invariants:**
- Promotions are idempotent
- Forgetting emits events AFTER write succeeds
- Maximum 1 promotion per memory per 60 seconds (throttle)
- Cascade delete is atomic (all-or-nothing)

### 8.3 MemoryOrchestrator (NEW)

**File:** `core/memory/orchestrator.py`

**Responsibility:** Entry point for all memory operations. Coordinates scoring, retention, and service.

```python
class MemoryOrchestrator:
    def __init__(
        self,
        memory_service: MemoryService,
        scoring_engine: ScoringEngine,
        retention_engine: RetentionEngine,
        retrieval_engine: RetrievalEngine,
        intelligence_service: MemoryIntelligenceService,
    ): ...
    
    async def store(
        self,
        content: str,
        source_type: str,
        metadata: Optional[dict] = None,
        importance: float = 0.5,
        confidence: float = 1.0,
        session_id: Optional[UUID] = None,
    ) -> UUID:
        """Store a new memory with scoring and tier assignment."""
        ...
    
    async def recall(
        self,
        request: MemoryRecallRequest,
        session_id: Optional[UUID] = None,
    ) -> MemoryRecallResponse:
        """Retrieve memories with scoring and ranking."""
        ...
    
    async def reflect(
        self,
        request: ReflectionRequest,
    ) -> bool:
        """Apply reflection to update memory confidence."""
        ...
    
    async def forget(
        self,
        chunk_id: UUID,
        reason: str,
        cascade: bool = False,
    ) -> bool:
        """Forget a memory (soft delete + event)."""
        ...
    
    async def archive(
        self,
        chunk_id: UUID,
        reason: str,
    ) -> bool:
        """Archive a memory (logical flag)."""
        ...
    
    async def promote(
        self,
        chunk_id: UUID,
        target_tier: MemoryTier,
    ) -> bool:
        """Manually promote a memory to a higher tier."""
        ...
    
    async def score(
        self,
        chunk_id: UUID,
    ) -> MemoryScoreDTO:
        """Calculate and return the score for a memory."""
        ...
```

**Invariants:**
- Sole entry point — routes and CLI never call repos directly
- All operations emit appropriate events
- All operations are idempotent where possible
- Score is calculated on every store and recall

### 8.4 MemoryConfig Extensions

**File:** `core/config.py`

```python
class MemoryScoringConfig(BaseModel):
    w_recency: float = 0.30
    w_frequency: float = 0.20
    w_confidence: float = 0.25
    w_importance: float = 0.15
    w_trust: float = 0.10
    lambda_decay: float = 0.05
    max_access_count: int = 1000

class MemoryRetentionConfig(BaseModel):
    l1_ttl_minutes: int = 10
    l1_max_items: int = 50
    l2_ttl_hours: int = 24
    l2_max_items: int = 200
    l2_promotion_threshold: float = 0.7
    l3_decay_threshold: float = 0.2
    archive_retention_days: int = 30
    promotion_throttle_seconds: int = 60

class MemoryConfig(BaseModel):
    scoring: MemoryScoringConfig = MemoryScoringConfig()
    retention: MemoryRetentionConfig = MemoryRetentionConfig()
```

---

## 9. API ROUTES

### 9.1 Memory Routes (FROZEN — CLI/API SYMMETRY)

**File:** `api/routes/memory.py`

API routes and CLI commands maintain strict one-to-one symmetry. Every API endpoint maps to exactly one CLI command. This mapping is frozen.

| API Endpoint | CLI Command | Description |
|-------------|-------------|-------------|
| `POST /api/v1/memory/store` | `jarvis memory store` | Store a new memory |
| `POST /api/v1/memory/recall` | `jarvis memory recall` | Retrieve memories with scoring |
| `GET /api/v1/memory/{id}` | `jarvis memory get` | Get a specific memory |
| `GET /api/v1/memory/{id}/score` | `jarvis memory score` | Get the score for a memory |
| `POST /api/v1/memory/{id}/reflect` | `jarvis memory reflect` | Apply reflection |
| `POST /api/v1/memory/{id}/forget` | `jarvis memory forget` | Forget a memory |
| `POST /api/v1/memory/{id}/archive` | `jarvis memory archive` | Archive a memory |
| `POST /api/v1/memory/{id}/promote` | `jarvis memory promote` | Promote to higher tier |
| `GET /api/v1/memory/stats` | `jarvis memory stats` | Get memory statistics |
| `GET /api/v1/memory/search` | `jarvis memory search` | Search memories by query |

### 9.2 Request/Response Contracts

```python
# Store
class MemoryStoreRequest(BaseModel):
    content: str
    source_type: str  # "codebase", "user_input", "web_page", "execution"
    metadata: Optional[dict] = None
    importance: float = 0.5
    confidence: float = 1.0

class MemoryStoreResponse(BaseModel):
    chunk_id: UUID
    tier: MemoryTier
    score: MemoryScoreDTO

# Recall
class MemoryRecallRequest(BaseModel):
    query: str
    max_chunks: int = 50
    max_tokens: int = 2000
    min_score: float = 0.0
    tier_filter: Optional[List[MemoryTier]] = None
    graph_depth: int = 0

class MemoryRecallResponse(BaseModel):
    chunks: List[MemoryChunkDTO]
    graph_nodes: List[MemoryNodeDTO]
    total_tokens: int
    scores: List[MemoryScoreDTO]
    metadata: RecallMetadata

# Stats
class MemoryStatsResponse(BaseModel):
    total_chunks: int
    chunks_by_tier: Dict[MemoryTier, int]
    average_score: float
    oldest_chunk_age_days: float
    newest_chunk_age_days: float
```

---

## 10. CLI COMMANDS

**File:** `memory/cli.py`

CLI commands mirror API endpoints one-to-one (frozen mapping in §9.1).

```
jarvis memory store <content> --source-type <type> [--importance <0-1>] [--confidence <0-1>]
jarvis memory recall <query> [--max-chunks <n>] [--tier <tier>]
jarvis memory get <chunk_id>
jarvis memory score <chunk_id>
jarvis memory reflect <chunk_id> --outcome <success|failure> [--delta <±0-1>]
jarvis memory forget <chunk_id> [--cascade]
jarvis memory archive <chunk_id>
jarvis memory promote <chunk_id> --tier <tier>
jarvis memory stats [--json]
jarvis memory search <query> [--json]
```

**Exit Codes:**
- 0: Success
- 1: Error (invalid args, not found)
- 8: Internal error

---

## 11. TEST STRATEGY

### 11.1 Test Categories

| Category | Count | Focus |
|----------|-------|-------|
| Unit: ScoringEngine | 10 | Score calculation, weight config, ranking |
| Unit: RetentionEngine | 10 | Promotion triggers, forgetting rules, throttle |
| Unit: MemoryOrchestrator | 10 | Integration of scoring + retention + service |
| API Routes | 10 | All endpoints, auth, error handling |
| CLI Commands | 10 | All commands, --json, exit codes |
| Integration | 10 | E2E store→recall→reflect→forget flow |
| **Total** | **60** | |

### 11.2 Test Fixtures

- SQLite in-memory database (no Postgres dependency)
- `MockEmbeddingGenerator` for vector operations
- `InMemoryVectorRepository` for vector store
- Deterministic timestamps for scoring tests
- Pre-seeded memory chunks for promotion/forgetting tests

---

## 12. MILESTONE BREAKDOWN

| Milestone | Description | Dependencies |
|-----------|-------------|--------------|
| M0 | ScoringEngine + MemoryScoringConfig | None |
| M1 | MemoryScoreDTO + score calculation | M0 |
| M2 | RetentionEngine + MemoryRetentionConfig | M0 |
| M3 | MemoryOrchestrator (coordinates all) | M0, M1, M2 |
| M4 | API Routes (10 endpoints) | M3 |
| M5 | CLI Commands (10 commands) | M3 |
| M6 | Integration Tests (60 tests) | M4, M5 |
| M7 | Quality Gate + Freeze | M6 |

---

## 13. RISKS AND MITIGATIONS

| Risk | Impact | Mitigation |
|------|--------|------------|
| Scoring formula too complex | Debugging difficulty | Start with 5 weights, log intermediate values |
| Promotion storms | Performance degradation | Throttle: 1 promotion per memory per 60s |
| Forgetting too aggressive | Data loss | Default to archive, not delete; 30-day retention |
| Memory tier confusion | Bugs in retrieval | Clear DTO separation per tier; tests verify tier isolation |
| Scoring weights need tuning | Suboptimal ranking | Configurable via config; A/B test in future phase |

---

## 14. CHANGE REQUESTS

| CR | Description | Status |
|----|-------------|--------|
| CR-1901 | Add Redis working memory (L1) | Future |
| CR-1902 | Real embedding provider (OpenAI/Ollama) | Future |
| CR-1903 | Cross-encoder re-ranking | Future |
| CR-1904 | S3/file-based archive pipeline | Future |
| CR-1905 | Memory encryption at rest | Future |

---

## 15. FROZEN INTERFACES

The following interfaces from Phase 1-18 remain frozen and must not be modified:

| Interface | File | Status |
|-----------|------|--------|
| IMemoryRepository | core/memory/interfaces.py | FROZEN |
| IVectorStoreRepository | core/memory/interfaces.py | FROZEN |
| IKnowledgeGraphRepository | core/memory/interfaces.py | FROZEN |
| IEmbeddingGenerator | core/memory/interfaces.py | FROZEN |
| MemoryService | core/memory/service.py | FROZEN |
| RetrievalEngine | core/memory/retrieval.py | FROZEN |
| MemoryIndexer | core/memory/indexer.py | FROZEN |
| MemoryIntelligenceService | core/memory/intelligence.py | FROZEN |

**New components added by this phase (NOT frozen yet):**
- ScoringEngine
- RetentionEngine
- MemoryOrchestrator
- MemoryScoringConfig
- MemoryRetentionConfig
- API Routes (memory)
- CLI (memory)

---

## 16. FROZEN CONTRACTS (Phase 19)

These contracts are immutable for Phase 19. Any modification requires a Change Request (CR).

### 16.1 Memory Identity Contract

Every memory entity MUST carry these immutable identity fields:

| Field | Type | Description |
|-------|------|-------------|
| `memory_id` | UUID | Unique identifier, never reused |
| `owner_id` | UUID | Entity that owns this memory (user, agent, system) |
| `session_id` | Optional[UUID] | Session that created this memory |
| `conversation_id` | Optional[UUID] | Conversation context |
| `created_at` | datetime | Immutable creation timestamp |
| `created_by` | str | Agent or system that created this |
| `memory_type` | MemoryType | Category (see §16.3) |
| `visibility` | MemoryVisibility | Access scope (see §16.4) |
| `trust_level` | TrustLevel | Source trust (see §3.3) |
| `confidence` | float | Accuracy confidence (0.0–1.0) |
| `version` | int | Monotonic version number |
| `source` | MemorySourceDTO | Provenance (see §16.2) |

### 16.2 Memory Provenance Contract

Every memory MUST carry provenance metadata:

| Field | Type | Description |
|-------|------|-------------|
| `origin` | str | Where this memory originated |
| `derived_from` | Optional[List[UUID]] | Parent memory IDs if derived |
| `created_by` | str | Agent/system that created |
| `updated_by` | Optional[str] | Agent/system that last updated |
| `reason` | Optional[str] | Why this memory was created/updated |
| `reflection_id` | Optional[UUID] | Reflection event that produced this |
| `workflow_id` | Optional[UUID] | Workflow that produced this |
| `agent_id` | Optional[UUID] | Agent that produced this |

### 16.3 Memory Types (FROZEN ENUM)

```python
class MemoryType(str, Enum):
    FACT = "fact"
    PREFERENCE = "preference"
    TASK = "task"
    GOAL = "goal"
    EVENT = "event"
    CONVERSATION = "conversation"
    RELATIONSHIP = "relationship"
    SYSTEM = "system"
    EPHEMERAL = "ephemeral"
```

### 16.4 Memory Visibility (FROZEN ENUM)

```python
class MemoryVisibility(str, Enum):
    PRIVATE = "private"       # Owner only
    USER = "user"             # All memories for a user
    SYSTEM = "system"         # System-wide read, kernel write
    AGENT = "agent"           # Active session agents
    PUBLIC = "public"         # All agents, all sessions
```

### 16.5 Knowledge Graph Node Types (FROZEN)

```python
class KGNodeType(str, Enum):
    PERSON = "Person"
    ORGANIZATION = "Organization"
    LOCATION = "Location"
    CONCEPT = "Concept"
    EVENT = "Event"
    TASK = "Task"
    GOAL = "Goal"
    SKILL = "Skill"
```

### 16.6 Knowledge Graph Edge Types (FROZEN)

```python
class KGEdgeType(str, Enum):
    KNOWS = "knows"
    WORKS_ON = "works_on"
    DEPENDS_ON = "depends_on"
    OWNS = "owns"
    RELATED_TO = "related_to"
    CAUSED_BY = "caused_by"
    USES = "uses"
```

### 16.7 Reflection Boundary (FROZEN)

Reflection may update memory. It must NOT modify:

- Skills (Phase 18 frozen)
- Planner decisions
- Workflows or orchestrators
- Runtime configuration
- Other agents' state

Self-improvement through reflection on code/skills/planner is deferred to Phase 23+.

### 16.8 Future Compatibility (FROZEN)

Memory implementation must remain independent of:

- Voice (Phase 24+)
- Vision (Phase 24+)
- Browser (Phase 24+)
- Desktop (Phase 24+)

These systems will plug into memory via controlled interfaces. Memory must not import or depend on any of these modules.

### 16.9 Memory Record Contract (FROZEN — Canonical Storage)

This is the canonical storage contract for all memory records. It defines the immutable schema contract across PostgreSQL, Vector DB, Graph DB, and future migrations.

```yaml
memory_record:
  # Identity (immutable after creation)
  memory_id: UUID                    # Primary key, never reused
  memory_type: MemoryType           # Fact, Preference, Task, Goal, Event, etc.
  
  # Ownership & Access
  owner_id: UUID                     # Entity that owns this memory
  visibility: MemoryVisibility      # Private, User, System, Agent, Public
  
  # Trust & Confidence
  trust_level: TrustLevel           # System, UserExplicit, UserImplicit, Learned, Inferred
  confidence: float                 # 0.0 – 1.0, updated by reflection
  importance: float                 # 0.0 – 1.0, assigned at creation
  
  # Timestamps
  created_at: datetime              # Immutable
  updated_at: datetime              # Updated on mutation
  expires_at: Optional[datetime]    # TTL expiry, null = never
  
  # Versioning
  version: int                      # Monotonic, incremented on update
  
  # Cross-references (representation links, not tiers)
  embedding_id: Optional[UUID]      # Vector store entry (if indexed)
  graph_node_id: Optional[UUID]     # Knowledge graph node (if linked)
  
  # Provenance
  provenance:                       # §16.2 contract
    origin: str
    derived_from: Optional[List[UUID]]
    created_by: str
    updated_by: Optional[str]
    reason: Optional[str]
    reflection_id: Optional[UUID]
    workflow_id: Optional[UUID]
    agent_id: Optional[UUID]
  
  # Content & Metadata
  content: str                      # The memory content
  content_hash: str                 # SHA-256 for dedup
  metadata: Optional[dict]          # Extensible key-value pairs
  token_count: int                  # For budget enforcement
```

**Invariants:**
- `memory_id` is assigned at creation, never reused even after deletion
- `created_at` is immutable after first write
- `version` is monotonic, never decremented
- `content_hash` is recomputed on every content change
- `embedding_id` and `graph_node_id` are representation links, not lifecycle dependencies
- All fields in this contract are mandatory unless marked Optional

---

## 17. ACCEPTANCE CRITERIA

1. All 60 tests pass
2. ScoringEngine produces deterministic scores for fixed inputs
3. RetentionEngine executes promotions and forgetting correctly
4. MemoryOrchestrator coordinates all operations without direct repo calls from routes/CLI
5. API routes handle all 10 endpoints correctly
6. CLI handles all 10 commands correctly
7. No frozen interfaces modified
8. No frozen contracts violated (§16)
9. No layer reversals (API → Core direction only)
10. Ruff format + check: clean
11. Mypy strict: zero errors
