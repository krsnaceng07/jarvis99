# 06_ARCHITECTURE_DECISION_RECORDS.md

## Purpose
This document compiles the Architecture Decision Records (ADRs) for JARVIS OS, tracking the design trade-offs, contexts, and justifications for core technical selections.

## Scope
Covers all system-level engineering choices across databases, API servers, task runner queues, sandboxes, UI clients, and automation tools.

## Architecture Decision Records (ADRs)

### ADR-01: Selection of FastAPI for API Core
- **Status:** Approved.
- **Context:** We need a high-performance backend supporting asynchronous execution, native WebSockets, and automatic Swagger generation.
- **Decision:** Use FastAPI (Python 3.11+).
- **Consequences:** Provides low-overhead routing, integrates natively with async database drivers (`asyncpg`), and handles WebSockets efficiently.

### ADR-02: PostgreSQL & pgvector for Relational and Vector Memory
- **Status:** Approved.
- **Context:** We need transactional storage for system configurations, memory indices, logs, and vector storage for embeddings.
- **Decision:** PostgreSQL with the `pgvector` extension.
- **Consequences:** Avoids running a separate Vector DB (e.g. Pinecone/Qdrant), keeping infrastructure requirements simple. Retains transactional integrity (ACID) and supports deep queries combining relational metadata with vector weights.

### ADR-03: Redis for Session & Active State Management
- **Status:** Approved.
- **Context:** Working memory, real-time message passing, and active task queues require sub-millisecond latencies.
- **Decision:** Redis 7.
- **Consequences:** Acts as the central pub-sub broker for agents, stores fast-decaying session data, and holds active task structures. Requires persistent backups to disk to prevent state loss on crash.

### ADR-04: Docker Containers for Local Tool Sandboxing
- **Status:** Approved.
- **Context:** Executing code, compiling skills, and running web scrapers poses a security risk to the host OS.
- **Decision:** Docker containerization.
- **Consequences:** Restricts file access, limits RAM/CPU allocations, and isolates network calls. Requires the local system to have Docker Desktop or Docker Engine installed.

### ADR-05: Electron Wrapper for Desktop Integration
- **Status:** Approved.
- **Context:** We need native window control, mouse/keyboard listeners, and file system APIs that Web browsers block by default.
- **Decision:** Electron.
- **Consequences:** Wraps the Next.js UI frontend and handles execution of native child processes locally. Requires careful IPC security limits to prevent frontend vulnerabilities from escaping to the host.

## Responsibilities
- **Lead Architect:** Add new ADR files or update existing entries before making structural modifications.
- **Reviewer Agent:** Check that code changes match the decisions recorded in this ADR index.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md).

## Interfaces
- Not applicable. This is a text-based compliance log.

## Examples
- **Correct Flow:** A developer wants to switch the database to MongoDB. They must draft ADR-06, discuss with the user, obtain approval, merge the ADR, and then rewrite DB modules.
- **Incorrect Flow:** A developer directly installs MongoDB and updates the source code. (Violates ADR review requirements).

## Failure Cases
- **Stale Records:** Architecture changes but ADRs are not updated. *Mitigation:* The Quality Gates check for code modifications changing system-level packages without matching updates in `/docs/06_ARCHITECTURE_DECISION_RECORDS.md`.

## Security Considerations
- Any decision to use cloud APIs for vector indexing or sandbox compilation must address data privacy risks inside a dedicated ADR entry.

## Future Extension
- Modifying or retiring an approved ADR entry requires creating a new ADR stating the migration rationale.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [04_TECHNICAL_REQUIREMENTS.md](file:///e:/jarvis/docs/04_TECHNICAL_REQUIREMENTS.md)
- [05_SYSTEM_ARCHITECTURE.md](file:///e:/jarvis/docs/05_SYSTEM_ARCHITECTURE.md)
