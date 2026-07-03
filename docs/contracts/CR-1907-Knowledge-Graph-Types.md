# CR-1907 — Knowledge Graph Node/Edge Type Set

**Status:** ✅ APPROVED (Option B — 8+7 types, spec-compliant) — 2026-07-03
**Date opened:** 2026-07-03
**Date decided:** 2026-07-03
**Decided by:** Architect (user)
**See:** [M5.5.0 freeze report](../reports/m5_5_0_freeze_report.md)
**Type:** Spec amendment (frozen document)
**Affects:** [docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md](docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md) §16.5, §16.6
**Related:**
- [docs/architecture/adrs/ADR-005-knowledge-graph.md](docs/architecture/adrs/ADR-005-knowledge-graph.md)
- [docs/contracts/knowledge_graph_contract.md](docs/contracts/knowledge_graph_contract.md) §3.1, §13
- [docs/adr/ADR-004_Knowledge_Graph.md](docs/adr/ADR-004_Knowledge_Graph.md)
- AGENTS.md §6.1 (Specification-First Resolution Rule)
- AGENTS.md §8 (Change Request Process)

---

## 1. Problem Statement

There is a **conflict** between the frozen Phase 19 spec and the user's verbally-stated design intent for the M6 Knowledge Graph node/edge type set.

| Source | KGNodeType count | KGEdgeType count |
|---|---|---|
| **Phase 19 spec §16.5/§16.6 (FROZEN 2026-06-30)** | 8 (PERSON, ORGANIZATION, LOCATION, CONCEPT, EVENT, TASK, GOAL, SKILL) | 7 (KNOWS, WORKS_ON, DEPENDS_ON, OWNS, RELATED_TO, CAUSED_BY, USES) |
| **User proposal (most recent, 2026-07-03)** | 10 (PERSON, ORGANIZATION, LOCATION, CONCEPT, EVENT, TASK, GOAL, SKILL, + 2 undecided) | 8 (existing 7 + 1 undecided) |
| **User earlier proposal (2026-06-29)** | 11 | 10 |
| **User earlier proposal (2026-06-30)** | 10 (USER, PROJECT, PERSON, LOCATION, DOCUMENT, TASK, SKILL, SESSION, FILE, MEMORY) | 9 |

**The conflict has not been resolved across 8 prior interactions.** Each time the agent has asked, the user has either iterated on the list or deferred. This blocks M6.0 implementation because:

1. The frozen DTOs (`core/memory/dto.py`) declare the 8+7 enum set.
2. Any deviation requires a CR per AGENTS.md §8.
3. The 5 freeze artifacts (contract, failure matrix, performance budget, observability contract, ADRs) all reference the 8+7 set with conditional "or extended" language.
4. CR-1907 is referenced but never formally recorded.

---

## 2. Proposed Resolution

This CR proposes **three explicit options** for the architect (user) to choose from. The agent will implement exactly the chosen option; no autonomous interpretation.

### Option A — ACCEPT (extend frozen spec to 10 + 8)
- **Node types (10):** PERSON, ORGANIZATION, LOCATION, CONCEPT, EVENT, TASK, GOAL, SKILL + **DOCUMENT**, **SESSION**
- **Edge types (8):** KNOWS, WORKS_ON, DEPENDS_ON, OWNS, RELATED_TO, CAUSED_BY, USES + **REFERENCES**
- **Effect:**
  - `core/memory/dto.py` enum extended (additive, no removal).
  - Spec §16.5/§16.6 amended with increment note.
  - All freeze artifacts (contract, failure matrix, performance budget, observability) updated to remove conditional language.
  - ADR-005 finalized without CR-1907 dependency note.
- **Migration:** Additive — no existing records broken. New enum values are accepted.
- **Risk:** Low. Slightly more types to test.

### Option B — REJECT (keep frozen 8 + 7)
- **Node types (8):** PERSON, ORGANIZATION, LOCATION, CONCEPT, EVENT, TASK, GOAL, SKILL (no change)
- **Edge types (7):** KNOWS, WORKS_ON, DEPENDS_ON, OWNS, RELATED_TO, CAUSED_BY, USES (no change)
- **Effect:**
  - `core/memory/dto.py` unchanged.
  - Spec §16.5/§16.6 unchanged.
  - All freeze artifacts (contract, failure matrix, performance budget, observability) updated to **remove** the conditional "or extended" language.
  - ADR-005 finalized with definitive spec §16.5/§16.6 reference.
- **Migration:** None needed.
- **Risk:** None. Cleanest path.

### Option C — DEFER (resolve per use case)
- The 8+7 base is implemented first.
- New types are added in M6.x follow-up sub-milestones (M6.1, M6.2, …) each with its own mini-CR.
- **Effect:**
  - Same as Option B for M6.0.
  - Future sub-milestones will have their own CRs.
- **Risk:** Slower. M6 ships lean, then grows.

---

## 3. Comparison

| Criterion | Option A (10+8) | Option B (8+7) | Option C (defer) |
|---|---|---|---|
| M6.0 ready | Yes | Yes | Yes |
| Spec amendment | Yes | No | No |
| Test surface | Larger | Smaller | Smaller (then grows) |
| Time to M6.0 | Same | Same | Same |
| Long-term flexibility | High | Medium | High |
| Implementation risk | Low | Lowest | Lowest |
| Governance overhead | Higher (1 CR now) | Lowest | Higher (N CRs later) |

---

## 4. Recommendation

**Option A** if the user has firm near-term needs for DOCUMENT, SESSION, REFERENCES.
**Option B** if the user's prior proposals were exploratory and the 8+7 set is sufficient.
**Option C** if the user wants to ship M6.0 quickly and defer type-set decisions until real graph queries expose the actual gap.

The agent's **default if no answer by 2026-07-10** is **Option B** (lowest risk, spec-compliant). The agent will not proceed with M6.0 implementation until one option is explicitly chosen.

---

## 5. Required Approvals

Per AGENTS.md §8 (Change Request Process):

| Role | Approval | Status |
|---|---|---|
| **Architect (user)** | Choose A / B / C | ⏳ PENDING |
| **Memory Lead** | (post-architect) | ⏳ PENDING |
| **Senior Engineer (1+)** | (post-architect) | ⏳ PENDING |

No agent may self-approve this CR.

---

## 6. Decision Recording

Once approved, this section will be filled in and the spec version incremented.

```
APPROVED ON: <YYYY-MM-DD>
OPTION:      <A | B | C>
SPEC VER:    1.0 → <NEW>
ARCHITECT:   <name>
MEMO:        <link to recording>
```

---

## 7. STOP Condition Active

Per AGENTS.md §6 (Automatic STOP Protocol) condition #11:

> "The implementation plan deviates from or contradicts the approved Phase Specification."

The agent has detected a deviation in the user's verbal direction vs. the frozen spec. Implementation of M6.0 is **BLOCKED** until this CR is resolved.

**Implementation Blocked Format:**

```
IMPLEMENTATION BLOCKED

Reason:            M6.0 KG type-set deviates from frozen spec §16.5/§16.6 (8+7 vs. user-proposed 10+8)
Affected files:    core/memory/dto.py (KGNodeType, KGEdgeType enums)
Conflicting source: docs/80_PHASE_19_REAL_MEMORY_ARCHITECTURE_SPECIFICATION.md §16.5, §16.6 (FROZEN)
Source A (Spec):    8 node types, 7 edge types (FROZEN 2026-06-30)
Source B (Verbal):  User-proposed 10 node types, 8 edge types (proposed 2026-07-03, unapproved)
Impact:            Architectural — change propagates to all M6 freeze artifacts, schema migration, tests
Recommended resolution: Approve CR-1907 with Option A, B, or C
Authority invoked: Rank 4 (Frozen spec) > Rank 1 (user instruction, must respect frozen boundary)

Waiting for architect approval. Not proceeding.
```

---

## 8. Versioning

- v1.0 (2026-07-03): CR opened. Status: PROPOSED.
- v1.1 (pending): Approved with chosen option, spec incremented, decision recorded.
