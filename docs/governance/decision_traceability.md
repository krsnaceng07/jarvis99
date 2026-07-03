# Decision Traceability — Governance System

**Status:** ✅ FROZEN — 2026-07-03 (M5.5.0)
**Version:** 1.0
**Date opened:** 2026-07-03
**Frozen by:** M5.5.0 (Engineering Governance Freeze)
**Authority:** AGENTS.md §1 (Authority Ranking), §8 (CR Process)
**Related:** RFC, ADR, EDL, Architecture Linter, Quality Gates Engine

---

## 1. Purpose

Decision Traceability ensures that **every engineering decision** is traceable from its origin (RFC or verbal direction) through ADR, Spec, Implementation, Tests, and Documentation. Six months from now, anyone can answer "why was this built this way?" with a single grep.

**Rule:** Every PR that introduces a behavioral or architectural change MUST update the decision-traceability matrix. A trace ID is mandatory in the PR description.

---

## 2. The 6-Link Trace Chain

```
[RFC-YYYY-NNN]  (origin: why was this proposed?)
       ↓
[ADR-YYYY-NNN]  (architecture: what was decided and what was rejected?)
       ↓
[Spec §X.Y]     (specification: what is the exact contract?)
       ↓
[Code path]     (implementation: which file/function/line?)
       ↓
[Test path]     (verification: which test proves the spec?)
       ↓
[Doc path]      (documentation: where is it documented for users?)
```

Each link MUST be present. Missing links = traceability gap = CI failure.

---

## 3. Trace ID Convention

- **Format:** `TRACE-{phase}-{milestone}-{nnn}`
- **Example:** `TRACE-19-M6-001` = Phase 19, M6, first trace.

A trace is created when a non-trivial decision is made. It is closed when all 6 links are populated.

---

## 4. Traceability Matrix

Filed as `docs/decisions/TRACE.md` (append-only, sorted by TRACE-ID).

```markdown
| TRACE-ID | RFC | ADR | Spec | Code | Test | Doc | Status |
|---|---|---|---|---|---|---|---|
| TRACE-19-M6-001 | RFC-2026-008 | ADR-005 | 80_PHASE_19 §16 | core/memory/kg/dto.py:42 | tests/test_kg_dto.py::test_node_creation | docs/contracts/knowledge_graph_contract.md §3.1 | CLOSED |
| TRACE-19-M6-002 | — | ADR-005 | 80_PHASE_19 §16.7 | core/memory/kg/repository.py:108 | tests/test_kg_repository.py::test_create_node_idempotent | docs/contracts/knowledge_graph_contract.md §13.1 | CLOSED |
```

**Status values:**
- **OPEN:** Some links missing.
- **CLOSED:** All 6 links present and verified.
- **SUPERSEDED:** Replaced by a later TRACE-ID (link in "RFC" column).

---

## 5. When a Trace Is Required

A new TRACE-ID MUST be opened when:

1. A new public DTO is added.
2. A new Repository method is added.
3. A new Service method is added.
4. A new event topic is added.
5. A new error type is added.
6. A new configuration option is added.
7. A new dependency is added.
8. A new architectural rule is enforced.
9. A new API endpoint is added.
10. A new CLI command is added.

A new TRACE-ID is NOT required for:
- Bug fixes (reference existing TRACE-ID of the feature being fixed).
- Refactors that do not change behavior.
- Documentation updates.
- Test additions to existing features.

---

## 6. The 6-Question Audit

For any trace, the following 6 questions must be answerable:

1. **Why was this built?** (link to RFC or verbal direction)
2. **What alternatives were considered?** (link to ADR)
3. **What is the exact contract?** (link to spec section)
4. **Where is the code?** (file path + line range)
5. **What proves the code matches the contract?** (test path)
6. **Where is it documented for users?** (doc path)

A trace that cannot answer all 6 questions is **OPEN** and blocks release.

---

## 7. Automated Trace Generation

The Architecture Linter can be extended to:
- Detect new public symbols in `core/**/dto.py`, `core/**/repository.py`, etc.
- Suggest a TRACE-ID for the PR.
- Verify the trace's `Code` link points to a valid file.
- (Optional) Auto-link to existing tests in `tests/**`.

This is a Phase 19 M5.5.x deliverable.

---

## 8. M6 Trace Backlog (initial)

| TRACE-ID | RFC | ADR | Spec | Code | Test | Doc | Status |
|---|---|---|---|---|---|---|---|
| TRACE-19-M6-001 | — | ADR-005 | 80_PHASE_19 §16.5 | core/memory/dto.py:KGNodeType | tests/test_memory_dto.py | docs/contracts/knowledge_graph_contract.md §3.1 | OPEN |
| TRACE-19-M6-002 | — | ADR-005 | 80_PHASE_19 §16.6 | core/memory/dto.py:KGEdgeType | tests/test_memory_dto.py | docs/contracts/knowledge_graph_contract.md §3.1 | OPEN |
| TRACE-19-M6-003 | — | ADR-005 | 80_PHASE_19 §16.7 | core/memory/dto.py:KGNode | tests/test_memory_dto.py | docs/contracts/knowledge_graph_contract.md §3.1 | OPEN |
| TRACE-19-M6-004 | — | ADR-005 | 80_PHASE_19 §16.8 | core/memory/dto.py:KGEdge | tests/test_memory_dto.py | docs/contracts/knowledge_graph_contract.md §3.1 | OPEN |
| TRACE-19-M6-005 | — | — | knowledge_graph_contract.md §3.2 | (future) core/memory/kg/repository.py | (future) tests/test_kg_repository.py | docs/contracts/knowledge_graph_contract.md §3.2 | OPEN |

**Rule:** M6.0 DTOs freeze must close TRACE-001 through TRACE-004. M6.1-M6.6 will close the rest.

---

## 9. Relationship to EDL and ADR

| Doc | Records | Format | Frequency |
|---|---|---|---|
| **RFC** | Why a major feature was proposed | Narrative | Once per phase |
| **ADR** | Why this architecture over alternatives | Narrative | Rare |
| **EDL** | What was decided today (operational) | Tabular | Frequent |
| **TRACE** | Where each decision is realized in code+test+docs | Tabular | Per public symbol |

All four are required. They serve different purposes:
- RFC = strategic intent
- ADR = architectural choice
- EDL = operational decision
- TRACE = implementation reality

---

## 10. Versioning

- v1.0 (2026-07-03): Decision Traceability introduced. 6-link chain, M6 initial backlog.
