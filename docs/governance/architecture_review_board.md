# Architecture Review Board (ARB) — Governance System

**Status:** ✅ FROZEN — 2026-07-03 (M5.5.0)
**Version:** 1.0
**Date opened:** 2026-07-03
**Frozen by:** M5.5.0 (Engineering Governance Freeze)
**Authority:** AGENTS.md §1, §5, §6, §8
**Related:** DRG (§2 of governance), RFC process, Pre-Milestone Gate, Engineering Decision Log

---

## 1. Purpose

The ARB is a **standing governance body** that approves or rejects major architectural changes **before** any code is written. It exists to prevent the failure mode observed in early-phase divergent implementations: building first, reviewing later (or never).

**Rule:** A feature/milestone that touches the frozen architecture (§4 of AGENTS.md) — including new components, new layers, new cross-cutting concerns, or new external dependencies — **MUST** receive an ARB decision before implementation begins.

---

## 2. Composition

| Role | Responsibility | Voting |
|---|---|---|
| **Chair (Architect)** | Owns the ARB process; final tie-breaker | Yes |
| **Memory Subsystem Lead** | Domain expert for the subsystem affected | Yes |
| **Security Agent** | Veto on security grounds (cannot be overridden) | Yes |
| **Senior Engineer (1+)** | Implementation reality check | Yes |
| **Scribe (rotating)** | Records decisions; non-voting | No |

**Quorum:** 3 voters including the Chair.
**Decision rule:** Simple majority. Security veto is absolute.

---

## 3. Trigger Conditions (ARB is REQUIRED for)

1. A new component, layer, or subsystem (e.g. Knowledge Graph, Workflow Engine, Browser Engine).
2. A new external dependency (DB engine, message queue, third-party API).
3. A change to the frozen architecture (AGENTS.md §4).
4. A new cross-cutting concern (auth, encryption, observability, rate limiting).
5. A milestone whose implementation plan deviates from the approved spec.
6. A deprecation or removal of a public interface.
7. A new data-classification tier (e.g. PII, secrets, audit data).

For minor changes (bug fixes, performance tweaks, doc updates), the ARB is **not** required — proceed under the standard Pre-Milestone Gate.

---

## 4. Process

```
Proposal
   ↓
ARB pre-read (1 week, all members review)
   ↓
ARB meeting (1 hour, recorded)
   ↓
Decision: APPROVED / APPROVED-WITH-CONDITIONS / REJECTED / DEFERRED
   ↓
ARB-YYYY-NNN record filed
   ↓
If APPROVED: continue to DRG (Design Review Gate)
```

---

## 5. ARB Record Template

Each ARB decision is filed as `ARB-YYYY-NNN-<short-name>.md` in `docs/governance/arb/`.

```markdown
# ARB-YYYY-NNN — <Decision Title>

**Status:** APPROVED | APPROVED-WITH-CONDITIONS | REJECTED | DEFERRED
**Date:** YYYY-MM-DD
**Chair:** <name>
**Voters:** <list>
**Affects:** <subsystem / spec / interface>

## Proposal
<2-3 paragraph summary of what was proposed>

## Risks Identified
- <risk 1>
- <risk 2>
- <risk 3>

## Alternatives Considered
| Alternative | Why Rejected |
|---|---|
| <alt 1> | <reason> |
| <alt 2> | <reason> |

## Decision
<APPROVED / APPROVED-WITH-CONDITIONS / REJECTED / DEFERRED>

## Conditions (if APPROVED-WITH-CONDITIONS)
1. <condition 1>
2. <condition 2>

## Rationale
<2-3 paragraphs>

## Sign-off
| Role | Name | Date |
|---|---|---|
| Chair | | |
| Memory Lead | | |
| Security Agent | | |
| Senior Engineer | | |
```

---

## 6. Checklist for Every ARB

- [ ] Proposal clearly identifies the change to frozen architecture (if any).
- [ ] At least 2 alternatives were considered and documented.
- [ ] Security Agent has reviewed for STRIDE threats (see `docs/governance/threat_modeling.md`).
- [ ] Performance budget exists (or is required as a condition).
- [ ] Compatibility matrix entry exists (or is required as a condition).
- [ ] Engineering Decision Log entry drafted.
- [ ] Rollback path identified.
- [ ] All 4-5 voters have signed (or abstained with reason).

---

## 7. ARB-2026-001 — Knowledge Graph Subsystem (M6)

**Status:** PROPOSED — pending user (architect) approval
**Date:** 2026-07-03
**Affects:** [docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md](docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md) §16, [docs/14_MEMORY_ENGINE_FREEZE.md](docs/14_MEMORY_ENGINE_FREEZE.md)

### Proposal
Add a new **Domain** component: the Knowledge Graph (KG), composed of `KGService`, `IKGRepository`, `KGValidator`, `TraversalEngine`, `InferenceEngine`. The KG stores entities and relationships extracted from `MemoryRecord` and exposes traversal, inference, and merge operations to the Memory Orchestrator.

### Risks Identified
1. **Cycle risk:** Traversal could enter infinite loops without strict cycle detection.
2. **Memory growth:** Unbounded nodes/edges could exhaust Postgres storage.
3. **Inference complexity:** Transitive closure and symmetric inference could return unexpectedly large result sets.
4. **Merge cascade:** Merging two high-degree nodes could rewrite thousands of edges inside one transaction.
5. **CR-1907 spec conflict:** Verbal user direction (10+8 types) vs. frozen spec (8+7).

### Alternatives Considered

| Alternative | Why Rejected |
|---|---|
| **PostgreSQL recursive CTE (chosen)** | Already a dependency. Supports bitemporal soft-delete. Predictable performance. |
| **NetworkX in-process** | No persistence; loses graph on restart; violates "no in-memory fallback" contract. |
| **Neo4j dedicated graph DB** | New infrastructure (violates "infrastructure minimalism" lesson). Operational overhead. |
| **Redis graph module** | Same as Neo4j — new infrastructure, new ops surface. |

### Decision
**PENDING** — awaiting CR-1907 resolution + user architect sign-off.

### Conditions (will be set after decision)
1. CR-1907 must be resolved (A / B / C) before M6.0 code.
2. Performance budget must be measurable at 100K nodes / 1M edges scale.
3. Inference must be **opt-in** (default: off) per [KG contract §13.4](docs/contracts/knowledge_graph_contract.md).
4. Merge operation must emit `kg.node.merged` event for auditability.

### Sign-off
| Role | Name | Date |
|---|---|---|
| Chair (Architect) | ⏳ pending | |
| Memory Lead | ⏳ pending | |
| Security Agent | ⏳ pending | |
| Senior Engineer | ⏳ pending | |
