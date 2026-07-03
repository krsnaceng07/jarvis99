# Design Review Gate (DRG) — Governance System

**Status:** ✅ FROZEN — 2026-07-03 (M5.5.0)
**Version:** 1.0
**Date opened:** 2026-07-03
**Frozen by:** M5.5.0 (Engineering Governance Freeze)
**Authority:** AGENTS.md §5 (Implementation Lifecycle)
**Related:** ARB, Pre-Milestone Gate, RFC process, Formal Interface Contract

---

## 1. Purpose

A Design Review Gate (DRG) is a **design-level review** that happens **after** ARB approval and **before** milestone implementation. It examines *how* the approved architecture will be realized, not *what* will be built (ARB handled that).

**Rule:** A milestone that has gone through ARB MUST pass DRG before any code in that milestone is written. DRG and ARB are **complementary**: ARB = "is this the right thing?"; DRG = "is the design correct?"

---

## 2. DRG vs ARB vs Pre-Milestone Gate

| Gate | Question | Stage | Output |
|---|---|---|---|
| **ARB** | "Is this the right thing to build? Does it fit the architecture?" | Before spec | ARB-YYYY-NNN record |
| **DRG** | "Is the design correct? Will it scale, recover, upgrade, roll back?" | After spec, before code | DRG-YYYY-NNN record |
| **Pre-Milestone Gate** | "Are all 12 governance items green?" | Right before code | PMG sign-off |

A milestone may go through DRG **multiple times** if its design is revised. ARB approval is one-shot per proposal.

---

## 3. The 6 Mandatory DRG Questions

For every design under DRG, these 6 questions MUST be answered. A "NO" or "unclear" answer blocks the gate.

1. **Scalability:** Does the design scale to 10x current expected load without architectural rework?
2. **Failure recovery:** What happens when each critical dependency fails? (DB, event bus, cache, external API.) Is the recovery automatic or manual?
3. **Observability:** Are metrics, logs, traces, and events defined for every public operation? (See `docs/observability/`.)
4. **Upgrade path:** Can the design be upgraded in-place? Is the data model versioned? Is there a forward + backward compatibility matrix? (See `docs/governance/compatibility_matrix.md`.)
5. **Rollback:** If this design ships and fails in production, can it be safely rolled back? Are migrations reversible? Is there a feature flag?
6. **Migration:** If existing data/code must change, is the migration step-by-step, tested, and reversible?

---

## 4. DRG Process

```
ARB APPROVED
   ↓
Author drafts design (interfaces, sequences, schemas, tests)
   ↓
DRG pre-read (3 days, 2 reviewers + 1 chair)
   ↓
DRG meeting (30 min, recorded)
   ↓
6 questions answered (all YES or N/A)
   ↓
Decision: PASS / PASS-WITH-COMMENTS / FAIL
   ↓
DRG-YYYY-NNN record filed
   ↓
Proceed to Pre-Milestone Gate → implementation
```

---

## 5. DRG Record Template

Each DRG decision is filed as `DRG-YYYY-NNN-<short-name>.md` in `docs/governance/drg/`.

```markdown
# DRG-YYYY-NNN — <Design Title>

**Status:** PASS | PASS-WITH-COMMENTS | FAIL
**Date:** YYYY-MM-DD
**ARB reference:** ARB-YYYY-NNN
**Reviewers:** <list>

## Design Summary
<2-3 paragraphs: what is being designed, what components, what flows>

## The 6 Questions

### 1. Scalability
**Answer:** <YES / NO / N/A>
**Evidence:** <link to load test, capacity plan, scaling strategy>

### 2. Failure recovery
**Answer:** <YES / NO / N/A>
**Evidence:** <link to failure matrix, chaos test plan>

### 3. Observability
**Answer:** <YES / NO / N/A>
**Evidence:** <link to observability contract, dashboard, alerts>

### 4. Upgrade path
**Answer:** <YES / NO / N/A>
**Evidence:** <link to compatibility matrix, versioned DTOs>

### 5. Rollback
**Answer:** <YES / NO / N/A>
**Evidence:** <link to rollback runbook, feature flag config>

### 6. Migration
**Answer:** <YES / NO / N/A>
**Evidence:** <link to migration script, test plan>

## Comments (if PASS-WITH-COMMENTS)
1. <comment 1>
2. <comment 2>

## Sign-off
| Role | Name | Date |
|---|---|---|
| Chair | | |
| Reviewer 1 | | |
| Reviewer 2 | | |
```

---

## 6. DRG-2026-001 — Knowledge Graph (M6) Design

**Status:** PROPOSED — pending user (architect) approval
**Date:** 2026-07-03
**ARB reference:** ARB-2026-001

### Design Summary
The M6 Knowledge Graph is implemented as a Domain-layer component with 5 internal sub-components: `KGService` (orchestration), `IKGRepository` (CRUD), `KGValidator` (input checks), `TraversalEngine` (graph queries), `InferenceEngine` (rule-based derivation). Data is persisted in PostgreSQL using a normalized schema with bitemporal versioning. Public interface is frozen in [docs/contracts/knowledge_graph_contract.md](docs/contracts/knowledge_graph_contract.md).

### The 6 Questions

#### 1. Scalability
**Answer:** YES
**Evidence:**
- [Performance budget](docs/performance/knowledge_graph_performance_budget.md) defines p50/p95/p99 targets up to 100K nodes / 1M edges.
- Indexes in [KG contract §13.9](docs/contracts/knowledge_graph_contract.md) cover all access patterns.
- Tested at 10K nodes / 50K edges in CI; extrapolated for production.

#### 2. Failure recovery
**Answer:** YES
**Evidence:**
- [Failure matrix](docs/failure/knowledge_graph_failure_matrix.md) lists 17 failure modes with mitigations.
- Repository raises `RepositoryUnavailableError` on DB failure — no silent in-memory fallback.
- Events use at-least-once delivery; consumers are idempotent.
- Optimistic concurrency (`expected_version`) prevents lost-update anomalies.

#### 3. Observability
**Answer:** YES
**Evidence:**
- [Observability contract](docs/observability/knowledge_graph_observability_contract.md) defines 10 event topics, 12 metrics, structured log format, 4 trace spans.
- All public operations emit `kg.query.completed` or `kg.query.failed`.
- Latency histograms tracked for p50/p95/p99.

#### 4. Upgrade path
**Answer:** YES
**Evidence:**
- All DTOs carry `schema_version: Literal["1.0"]`.
- Type enums are additive-only (no removal without CR).
- [Compatibility matrix](docs/compatibility/m6_compatibility_matrix.md) maps DTO v1 → Validator v1 → Repository v1 → API v1 → CLI v1.

#### 5. Rollback
**Answer:** YES (with feature flag)
**Evidence:**
- Feature flag: `kg.enabled` (default `true` in v1, but flag-gated for staged rollout).
- DB migration is forward-only (additive columns/indexes) and reversible via a sibling down-migration.
- Soft-delete (`valid_to`) means no destructive rollback needed.
- Consumers (Memory Orchestrator) fall back to flat memory queries if KG is disabled.

#### 6. Migration
**Answer:** YES
**Evidence:**
- No existing KG data → no backfill needed.
- Existing `MemoryRecord` records need no schema change.
- New `kg_nodes` and `kg_edges` tables created in M6.0 migration `m6_001_create_kg_nodes.sql`.
- Indexes added in M6.1 migration `m6_002_add_kg_indexes.sql`.

### Comments
None.

### Sign-off
| Role | Name | Date |
|---|---|---|
| Chair (Architect) | ⏳ pending | |
| Reviewer 1 | ⏳ pending | |
| Reviewer 2 | ⏳ pending | |
