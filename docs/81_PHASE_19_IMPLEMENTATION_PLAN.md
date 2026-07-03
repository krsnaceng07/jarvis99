# PHASE 19 — REAL MEMORY ARCHITECTURE IMPLEMENTATION PLAN

**STATUS:** FROZEN
**VERSION:** 1.1 (plan amendment 2026-07-03: M5.5 inserted)
**DATE:** 2026-06-30
**FREEZE_DATE:** 2026-06-30
**LAST_AMENDMENT:** 2026-07-03 (CR-1908, M5.5 inserted; spec unchanged)
**SPEC:** `docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md`
**SCOPE:** Implement the memory intelligence layer on top of existing memory foundation.

---

## 1. OBJECTIVE

Build the Real Memory Architecture as specified in `docs/80`, implementing:
- Memory scoring with the frozen formula
- Promotion and forgetting lifecycle
- Retrieval pipeline with frozen order
- Memory Orchestrator as sole coordination layer
- API routes and CLI as thin adapters

**Core principle:** API/CLI may only call `MemoryOrchestrator`. No direct calls to repositories, scoring, retention, or knowledge graph.

---

## 2. DEPENDENCY CHAIN

```
M0 (DTO)
  ↓
M1 (Validator)
  ↓
M2 (Repository)
  ↓
M3 (Scoring Engine)
  ↓
M4 (Retrieval Engine)
  ↓
M5 (Retention Engine)
  ↓
M5.5 (Engineering Governance Freeze)  ← inserted 2026-07-03 per CR-1908
  ↓
M6 (Knowledge Graph)
  ↓
M7 (Orchestrator)
  ↓
M8 (API)
  ↓
M9 (CLI)
  ↓
M10 (Integration)
  ↓
M11 (Freeze Gate)
```

Each milestone depends on the previous. No parallel execution across the chain.

**M5.5 is a non-code meta-milestone** that freezes the 13 governance documents and 6 custom tooling scripts required for M6+. See [docs/phases/phase19/m5_5_engineering_governance_freeze.md](phases/phase19/m5_5_engineering_governance_freeze.md) for full definition. CR-1908 must be approved before M5.5 sub-milestones begin.

---

## 3. MILESTONE DETAILS

### M0 — Memory DTO Layer

**Files:** `core/memory/dto.py`

**Deliverables:**
- `MemoryRecord` — canonical storage contract (§16.9 of spec)
- `MemoryMetadata` — extensible metadata wrapper
- `MemoryScore` — score breakdown (recency, semantic, confidence, importance, frequency, trust, pin)
- `RetrievalRequest` — recall parameters (query, filters, budget)
- `RetrievalResponse` — ranked results with metadata
- `ReflectionRequest` — post-execution reflection input
- `ReflectionResponse` — reflection outcome
- `ArchiveRequest` — archive parameters
- `PromotionRequest` — manual promotion input

**Constraints:**
- No IO
- No repository
- No scoring logic
- No database

**Gate:** Ruff + mypy + DTO tests

---

### M1 — Memory Validator

**Files:** `core/memory/validator.py`

**Deliverables:**
- Visibility validation (§16.4 enum values)
- Provenance validation (§16.2 contract fields)
- Identity validation (§16.1 contract fields)
- Trust level validation (§3.3 enum values)
- Metadata validation (size limits, type checks)
- Version validation (monotonic, non-decreasing)
- Memory type validation (§16.3 enum values)

**Constraints:**
- No repository
- No scoring
- No retrieval
- Pure validation functions

**Gate:** Ruff + mypy + validator tests

---

### M2 — Repository Layer

**Files:** `core/memory/repository.py` (extend existing)

**Deliverables:**
- CRUD operations for MemoryRecord
- Soft delete with archival flag
- Content hash deduplication
- Version tracking
- Visibility-scoped queries

**Constraints:**
- No ranking
- No promotion
- No scoring
- No orchestration
- CRUD + transactions + versioning ONLY

**Gate:** Ruff + mypy + repository tests

---

### M3 — Scoring Engine

**Files:** `core/memory/scoring.py`

**Deliverables:**
- `ScoringEngine` class with frozen formula
- `calculate_score(chunk, access_count, last_accessed, source_trust, now)` → `MemoryScore`
- `rank_chunks(chunks, access_counts, source_trusts, now)` → `List[MemoryScore]`
- Configurable weights via `MemoryScoringConfig`

**Frozen Formula:**
```
FinalScore = Recency + SemanticSimilarity + Confidence + Importance + Frequency + Trust + UserPin
```

**Constraints:**
- Pure functions only
- No IO
- Deterministic
- 100% test coverage

**Gate:** Ruff + mypy + scoring tests (determinism verified)

---

### M4 — Retrieval Engine

**Files:** `core/memory/retrieval.py` (extend existing)

**Deliverables:**
- Frozen pipeline order implementation:
  1. Intent Analysis
  2. Permission Filter (BEFORE candidate generation)
  3. Candidate Generation (L0, L1, L2, L3)
  4. Vector Search
  5. Knowledge Graph Expansion
  6. Hybrid Merge (RRF fusion)
  7. Scoring
  8. Ranking
  9. Context Compression

**Constraints:**
- No API
- No CLI
- Follows frozen order exactly
- Permission filter before candidate generation

**Gate:** Ruff + mypy + retrieval tests

---

### M5 — Retention Engine

**Files:** `core/memory/retention.py`

**Deliverables:**
- `RetentionEngine` class
- `evaluate_promotions(session_id, now)` → `List[PromotionAction]`
- `evaluate_forgetting(now)` → `List[ForgettingAction]`
- `archive_chunk(chunk_id, reason)` → `bool`
- `cascade_delete(source_id, reason)` → `int`
- Promotion triggers: L1→L2 (access_count >= 3), L2→L3 (score >= 0.7)
- Forgetting triggers: TTL expiry, score decay, manual, cascade, GDPR
- Throttle: max 1 promotion per memory per 60 seconds
- Idempotent operations

**Constraints:**
- No repository writes outside orchestrator callbacks
- Emits events AFTER write succeeds
- Atomic cascade delete

**Gate:** Ruff + mypy + retention tests

---

### M6 — Knowledge Graph

**Files:** `core/memory/graph.py` (extend existing), `core/memory/kg/` (new sub-package per M5.5 Architecture Linter)

**Deliverables:**
- Frozen node types (§16.5): Person, Organization, Location, Concept, Event, Task, Goal, Skill
- Frozen edge types (§16.6): knows, works_on, depends_on, owns, related_to, caused_by, uses
- Node CRUD
- Edge CRUD
- BFS traversal with cycle avoidance
- Graph expansion for retrieval

**Constraints:**
- No vector logic
- No scoring
- Graph operations only

**Prerequisite:** M5.5 must be FROZEN. M6 code must pass the Architecture Linter, DGV, and QGE on every commit. See [docs/contracts/m6_master_checklist.md](contracts/m6_master_checklist.md).

**Gate:** Ruff + mypy + graph tests + Architecture Linter + DGV + RRG (8 items)

---

### M7 — Memory Orchestrator

**Files:** `core/memory/orchestrator.py`

**Deliverables:**
- `MemoryOrchestrator` class
- `store(content, source_type, metadata, importance, confidence, session_id)` → `UUID`
- `recall(request, session_id)` → `RetrievalResponse`
- `reflect(request)` → `bool`
- `forget(chunk_id, reason, cascade)` → `bool`
- `archive(chunk_id, reason)` → `bool`
- `promote(chunk_id, target_tier)` → `bool`
- `score(chunk_id)` → `MemoryScore`

**Coordination:**
- Sole entry point for all memory operations
- Coordinates: Repository, Scoring, Retention, KG, EventBus
- All operations emit appropriate events
- Score calculated on every store and recall

**Constraints:**
- Only component that may call all subsystems
- Routes and CLI never call repos directly
- All operations idempotent where possible

**Gate:** Ruff + mypy + orchestrator tests

---

### M8 — API Routes

**Files:** `api/routes/memory.py`

**Deliverables:**
- 10 REST endpoints (frozen mapping in §9.1):
  - `POST /api/v1/memory/store`
  - `POST /api/v1/memory/recall`
  - `GET /api/v1/memory/{id}`
  - `GET /api/v1/memory/{id}/score`
  - `POST /api/v1/memory/{id}/reflect`
  - `POST /api/v1/memory/{id}/forget`
  - `POST /api/v1/memory/{id}/archive`
  - `POST /api/v1/memory/{id}/promote`
  - `GET /api/v1/memory/stats`
  - `GET /api/v1/memory/search`

**Constraints:**
- Thin adapter only
- Only calls MemoryOrchestrator
- No business logic
- No direct repo calls

**Gate:** Ruff + mypy + API tests

---

### M9 — CLI Commands

**Files:** `memory/cli.py`

**Deliverables:**
- 10 CLI commands (frozen mapping in §9.1):
  - `jarvis memory store`
  - `jarvis memory recall`
  - `jarvis memory get`
  - `jarvis memory score`
  - `jarvis memory reflect`
  - `jarvis memory forget`
  - `jarvis memory archive`
  - `jarvis memory promote`
  - `jarvis memory stats`
  - `jarvis memory search`

**Constraints:**
- Thin adapter only
- Only calls MemoryOrchestrator
- No business logic
- `--json` flag support
- Exit codes: 0=success, 1=error, 8=internal

**Gate:** Ruff + mypy + CLI tests

---

### M10 — Integration Tests

**Files:** `tests/test_memory_integration.py`

**Deliverables:**
- E2E lifecycle: Store → Score → Promote → Retrieve → Reflect → Archive → Forget
- Cross-component verification
- Permission filter verification
- Promotion idempotency verification
- Forgetting throttle verification
- Event emission verification
- Budget enforcement verification
- Frozen contract compliance verification

**Target:** 60 tests across 6 categories

**Gate:** Ruff + mypy + all tests pass

---

### M11 — Freeze Gate

**Deliverables:**
- Full repository quality gate (ruff + mypy + pytest)
- Architecture audit (no layer reversals, no forbidden imports)
- `PHASE19_FREEZE_REPORT.md`
- AGENTS.md Phase Status Board update
- 60_MASTER_INDEX.md update

**Gate:** All gates pass, freeze report generated

---

## 4. ARCHITECTURE BOUNDARIES (Frozen)

```
DTO → Validator → Repository → Scoring → Retrieval → Retention → KG → Orchestrator → API → CLI
```

**Rules:**
- Never bypass layers
- DTO is the contract boundary
- Validator is pure validation
- Repository is CRUD only
- Scoring is pure function
- Retrieval follows frozen pipeline order
- Retention manages lifecycle
- KG manages entity relationships
- Orchestrator is sole coordinator
- API/CLI are thin adapters

---

## 5. ACCEPTANCE CRITERIA

Every milestone must satisfy:
- Ruff clean
- mypy clean
- milestone tests 100% pass
- no forbidden imports
- no layer reversal
- no frozen interface modification
- authority audit pass

**No milestone proceeds until architect approval.**

---

## 6. FROZEN INTERFACES (Phase 1–18)

These interfaces must NOT be modified:

| Interface | File |
|-----------|------|
| IMemoryRepository | core/memory/interfaces.py |
| IVectorStoreRepository | core/memory/interfaces.py |
| IKnowledgeGraphRepository | core/memory/interfaces.py |
| IEmbeddingGenerator | core/memory/interfaces.py |
| MemoryService | core/memory/service.py |
| RetrievalEngine | core/memory/retrieval.py |
| MemoryIndexer | core/memory/indexer.py |
| MemoryIntelligenceService | core/memory/intelligence.py |

---

## 7. KNOWN CHANGE REQUESTS (Future)

| CR | Description | Phase |
|----|-------------|-------|
| CR-1901 | Redis working memory (L1) | Future |
| CR-1902 | Real embedding provider (OpenAI/Ollama) | Future |
| CR-1903 | Cross-encoder re-ranking | Future |
| CR-1904 | S3/file-based archive pipeline | Future |
| CR-1905 | Memory encryption at rest | Future |

---

## 8. SUCCESS DEFINITION

Phase 19 is complete only when:
- Memory scoring is deterministic
- Retrieval pipeline follows frozen order
- Promotion/retention are idempotent
- MemoryOrchestrator is the only coordination layer
- API and CLI remain thin adapters
- Existing frozen interfaces remain unchanged
- Full repository quality gate passes
- Architecture audit passes
- Phase 19 freeze report is generated

---

**Implementation blocked until architect approval of this plan.**
