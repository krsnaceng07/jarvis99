# Architecture Decision Records (ADRs)

This directory is the **canonical registry** for Architecture Decision Records (ADRs) for JARVIS OS. It tracks the context, decision status, and consequences of critical system design trade-offs.

> **Note:** As of 2026-07-10, all ADRs are consolidated here from:
> - The legacy `docs/adr/` location (earlier consolidation).
> - The legacy `docs/06_ARCHITECTURE_DECISION_RECORDS.md` file (ADR-01..05 migrated as ADR-012..016 on 2026-07-10 during Phase A → Phase E cleanup).
>
> See git history for migration trail and `.audit/CLEANUP_REPORT.md` for the consolidation record.

## Active ADR Index

| ADR ID | Title | Status |
| --- | --- | --- |
| **ADR-001** | [EventBus Architecture & Message Schemas](ADR-001-event-bus.md) | Accepted |
| **ADR-002** | [Memory Records Storage Strategy](ADR-002-memory-storage.md) | Accepted |
| **ADR-003** | [Tiered Memory Architecture & Promotion](ADR-003-tiered-memory.md) | Accepted |
| **ADR-004** | [Retrieval Pipeline Design](ADR-004-retrieval-pipeline.md) | Accepted |
| **ADR-005** | [Scoring Engine — 7 Weights and Pure Functions](ADR-005-scoring-engine.md) | Accepted |
| **ADR-006** | [Retention Policy](ADR-006-retention-policy.md) | Accepted |
| **ADR-007** | [Dynamic Skill System Runtime & Isolation](ADR-007-skill-runtime.md) | Accepted |
| **ADR-008** | [JSON-Envelope Multi-Agent Protocol](ADR-008-multi-agent.md) | Accepted |
| **ADR-009** | [Relational Knowledge Graph BFS Traversal](ADR-009-kg-bfs.md) | Accepted |
| **ADR-010** | [Knowledge Graph Storage Strategy](ADR-010-kg-storage.md) | Accepted |
| **ADR-011** | [Knowledge Graph — Identity, Versioning, Inference](ADR-011-kg-identity.md) | Proposed |
| **ADR-012** | [FastAPI as API Core Framework](ADR-012-fastapi.md) | Accepted (migrated 2026-07-10) |
| **ADR-013** | [PostgreSQL + pgvector for Relational & Vector Memory](ADR-013-postgresql-pgvector.md) | Accepted (migrated 2026-07-10) |
| **ADR-014** | [Redis 7 for Session & Active State](ADR-014-redis.md) | Accepted (migrated 2026-07-10) |
| **ADR-015** | [Docker Containers for Tool Sandboxing](ADR-015-docker-sandboxing.md) | Accepted (migrated 2026-07-10) |
| **ADR-016** | [Electron Wrapper for Desktop Integration](ADR-016-electron-desktop.md) | Accepted (migrated 2026-07-10) |

## Naming Convention

- Format: ADR-XXX-kebab-case-name.md
- Numbering: sequential, by topic domain (foundation → operations → features)
- All ADRs live in this directory (canonical location)

## Adding a New ADR

1. Copy ADR_TEMPLATE.md
2. Use next sequential number (ADR-012, etc.)
3. Add row to index above
4. Update related ADRs if cross-references change
