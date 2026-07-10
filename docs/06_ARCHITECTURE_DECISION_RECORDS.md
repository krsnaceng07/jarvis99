# 06_ARCHITECTURE_DECISION_RECORDS.md

## ⚠️ STATUS: LEGACY POINTER FILE (DEPRECATED FORMAT)

> **Canonical ADR registry:** [`docs/architecture/adrs/`](architecture/adrs/)
>
> This file is preserved as a navigable legacy entry from the Phase 0 Foundation Wave (it is referenced by `docs/60_MASTER_INDEX.md`, `docs/04_TECHNICAL_REQUIREMENTS.md`, `docs/05_SYSTEM_ARCHITECTURE.md`, `docs/07_DESIGN_PRINCIPLES.md`, and `docs/architecture/01_ARCHITECTURE_FREEZE.md`). Its content has been replaced with a migration pointer table to the canonical ADR registry. The original 5 ADR entries (FastAPI, PostgreSQL, Redis, Docker, Electron) were migrated to canonical Nygard format on **2026-07-10** during the documentation governance cleanup.
>
> **Authority for canonical location:** [`docs/governance/pre_milestone_gate.md`](governance/pre_milestone_gate.md) §2.2 — frozen M5.5.0 (2026-07-03) explicitly states: *"File path under `docs/architecture/adrs/` with the prescribed structure (Context, Decision, Alternatives, Consequences, Future Changes)"*.

---

## Purpose (Historical)

This document originally compiled the Architecture Decision Records (ADRs) for JARVIS OS in a single inline file, tracking the design trade-offs, contexts, and justifications for foundational technical selections.

**The new format** (per canonical registry) uses one Markdown file per ADR with the Michael Nygard structure: Status → Context → Decision → Consequences → Compliance & Invariants.

---

## Scope (Historical)

Covered foundational system-level engineering choices across databases, API servers, task runner queues, sandboxes, UI clients, and automation tools.

The new canonical registry continues this scope AND also covers architecture-pattern decisions (event bus, memory tiers, scoring, knowledge graph).

---

## ADR Migration Map

| Legacy ID | Title | Canonical ADR |
|-----------|-------|---------------|
| ADR-01 | Selection of FastAPI for API Core | [ADR-012](architecture/adrs/ADR-012-fastapi.md) |
| ADR-02 | PostgreSQL & pgvector for Relational and Vector Memory | [ADR-013](architecture/adrs/ADR-013-postgresql-pgvector.md) |
| ADR-03 | Redis for Session & Active State Management | [ADR-014](architecture/adrs/ADR-014-redis.md) |
| ADR-04 | Docker Containers for Local Tool Sandboxing | [ADR-015](architecture/adrs/ADR-015-docker-sandboxing.md) |
| ADR-05 | Electron Wrapper for Desktop Integration | [ADR-016](architecture/adrs/ADR-016-electron-desktop.md) |

All five entries were migrated on 2026-07-10 with full content preservation and Nygard-format upgrade. The canonical versions add: Alternatives Considered, Compliance & Invariants, and References sections.

The current canonical registry contains **16 ADRs (ADR-001 through ADR-016)** covering both foundational tech stack choices (ADR-012..016) and architecture-pattern decisions (ADR-001..011).

---

## Responsibilities (Historical, Now Updated)

- **Lead Architect:** Add new ADRs **only** to `docs/architecture/adrs/` (canonical). Update `docs/architecture/adrs/README.md` index when adding.
- **Reviewer Agent:** Check that code changes match the decisions recorded in the **canonical** ADR registry. PRs that change tech-stack packages without matching ADR updates in `docs/architecture/adrs/` are blocked by quality gates.

---

## Interfaces

- This file: **navigational pointer only.** Add no new ADRs here.
- Canonical registry: [`docs/architecture/adrs/README.md`](architecture/adrs/README.md)

---

## Failure Cases

- **Stale Records:** Architecture changes but ADRs are not updated. *Mitigation:* The Quality Gates check for code modifications changing system-level packages against the **canonical registry** at `docs/architecture/adrs/`, not this file.

---

## Security Considerations

- Unchanged from original: any decision to use cloud APIs for vector indexing or sandbox compilation must address data privacy risks inside a dedicated ADR entry (now filed under canonical registry).

---

## Future Extension

- This file will be **removed** in a future cleanup once external links to it are also updated. Until then, it serves as a redirect stub.

---

## Related Documents

- **Canonical:** [`docs/architecture/adrs/README.md`](architecture/adrs/README.md) — Architecture Decision Records registry (16 ADRs)
- **Authority for location:** [`docs/governance/pre_milestone_gate.md`](governance/pre_milestone_gate.md) §2.2 — frozen M5.5.0
- [`00_PROJECT_CONSTITUTION.md`](00_PROJECT_CONSTITUTION.md) — ADR rules
- [`04_TECHNICAL_REQUIREMENTS.md`](04_TECHNICAL_REQUIREMENTS.md) — TRD
- [`05_SYSTEM_ARCHITECTURE.md`](05_SYSTEM_ARCHITECTURE.md) — system architecture

---

## Migration Audit Trail

- **2026-07-10 (Phase A → E cleanup):** Original ADR-01..05 content migrated to canonical `docs/architecture/adrs/ADR-012..016`. This file converted to a legacy pointer stub preserving file path. See `.audit/CLEANUP_REPORT.md` for full record.
