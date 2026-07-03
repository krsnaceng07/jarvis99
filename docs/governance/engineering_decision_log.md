# Engineering Decision Log (EDL) — Governance System

**Status:** ✅ FROZEN — 2026-07-03 (M5.5.0)
**Version:** 1.0
**Date opened:** 2026-07-03
**Frozen by:** M5.5.0 (Engineering Governance Freeze)
**Authority:** AGENTS.md §1 (Authority Ranking)
**Related:** ADR (Architecture Decision Records), Engineering Decision Log, Change Request

---

## 1. Purpose

The Engineering Decision Log (EDL) records **every important engineering decision** made during a milestone — not just architectural ones. ADRs record *why we chose X over Y* (architectural). EDL records *what we decided, who decided, when, with what rationale, and how to undo it* (operational).

**Rule:** Every decision that:
- Changes a public interface
- Adds a dependency
- Changes a configuration default
- Accepts a known risk
- Defers a known issue

MUST be logged in the EDL. The log is append-only. The log is searchable.

---

## 2. EDL vs ADR

| | ADR | EDL |
|---|---|---|
| **Scope** | Architectural (large, lasting) | Engineering (any size) |
| **Frequency** | Rare (~1 per major decision) | Frequent (~5-20 per milestone) |
| **Format** | Narrative (Context → Decision → Alternatives → Consequences) | Tabular (one line per entry) |
| **Audience** | Architects, future maintainers (months later) | Current team, on-call (days/weeks later) |
| **Examples** | "Why PostgreSQL over Neo4j" | "Why we deferred inference result-set cap from 10K to 50K" |

**Both are required.** ADR answers "why this architecture?"; EDL answers "what did we decide today?"

---

## 3. EDL Entry Format

Each entry is one row in the log file `docs/decisions/EDL.md`.

```markdown
| EDL-ID | Date | Decision | Owner | Reason | Alternative | Impact | Rollback | Review Date |
|---|---|---|---|---|---|---|---|---|
| EDL-001 | 2026-07-03 | Use SQLAlchemy 2.0 async for KG Repository | <name> | <reason> | <alt considered> | <impact> | <rollback steps> | <YYYY-MM-DD> |
```

**Fields:**
- **EDL-ID:** Sequential per log file, e.g. `EDL-001`, `EDL-002`. Never reused.
- **Date:** YYYY-MM-DD.
- **Decision:** One-line summary. Verifiable from the code/config it references.
- **Owner:** Name (or role) of the person who made the call.
- **Reason:** 1-2 sentences. Why this choice?
- **Alternative:** What was rejected? (Often a single word; the EDL is not the place for the full analysis — that's the ADR.)
- **Impact:** What changes? (One line.)
- **Rollback:** How to undo this decision if it turns out wrong. (One line — if non-trivial, link to runbook.)
- **Review Date:** YYYY-MM-DD. When should this decision be re-examined? (Default: 6 months.)

---

## 4. EDL Log File Location

`docs/decisions/EDL.md` — append-only, sorted by EDL-ID ascending.

A milestone may have its own EDL sub-log if it grows large: `docs/decisions/edl_m6_knowledge_graph.md`. The main log links to it.

---

## 5. EDL-2026 — Knowledge Graph (M6) Decisions

This is the sub-log for M6. It will grow as the milestone progresses.

| EDL-ID | Date | Decision | Owner | Reason | Alternative | Impact | Rollback | Review Date |
|---|---|---|---|---|---|---|---|---|
| EDL-M6-001 | 2026-07-03 | Use `asyncpg` (raw SQL) for KG Repository, not SQLAlchemy | Memory Lead | Predictable perf, fewer abstractions, smaller surface for SQL injection | SQLAlchemy 2.0 async | Lower query overhead; no ORM convenience | Swap repository impl; tests must cover both paths | 2026-12-03 |
| EDL-M6-002 | 2026-07-03 | Default `inference_enabled = False` at the service level | Architect | Inference is opt-in per contract §13.4; default-off prevents accidental activation | Default-on | Safer rollout; orchestrator must explicitly request inference | Flip default; no data migration | 2026-10-03 |
| EDL-M6-003 | 2026-07-03 | `properties` JSON size capped at 64KB | Architect | DoS protection (see STRIDE TM-2026-001 §D) | 1MB | Prevents memory/CPU DoS; large graphs force decomposition into multiple edges | Raise cap; requires DTO + validator change (MINOR) | 2026-12-03 |
| EDL-M6-004 | 2026-07-03 | Merge operation is manual-only (no automatic dedup) | Architect | M6 is v1.0; auto-merge is risky. Manual keeps auditability | Auto-merge with confidence threshold | Safer; orchestrator owns dedup policy | Add auto-merge service in M6.x; CR required | 2026-12-03 |
| EDL-M6-005 | 2026-07-03 | Cycle in graph is **permitted** in data model; traversal prevents infinite loops | Memory Lead | Real-world graphs may have cycles; traversal is the only place that can break | Forbid cycles at write time | More flexible data model; traversal complexity is bounded by visited-set | Forbid cycles; requires data migration | 2026-12-03 |
| EDL-M6-006 | 2026-07-03 | Inference result set capped at 10K nodes | Architect | Prevents OOM on large transitive closures | Unlimited | Bounded memory; large inferences must paginate | Raise cap; CR required (MAJOR) | 2026-12-03 |

---

## 6. Process

1. **Decide:** During a meeting, code review, or DRG, a decision is made.
2. **Log:** Within 24 hours, the decision is added to `docs/decisions/EDL.md` (or the milestone sub-log) with all 9 fields filled.
3. **Review:** On the "Review Date", the team re-examines the decision. Update the log with a "reviewed" note and any supersession.
4. **Supersede:** If a decision is reversed, append a new EDL entry that references the old one (e.g. "EDL-M6-007: Supersedes EDL-M6-001 — switched to SQLAlchemy for consistency with other repositories"). Do NOT edit the old entry.

---

## 7. Tools

A simple grep over `docs/decisions/EDL.md` is the primary search tool. For larger projects, a `scripts/edl_query.py` helper can be added to filter by owner, date, or topic.

---

## 8. Versioning

- v1.0 (2026-07-03): EDL system introduced. Sub-log `EDL-M6-*` opened for Knowledge Graph milestone.
