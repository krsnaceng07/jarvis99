# 04_TECHNICAL_REQUIREMENTS.md

## Purpose
This document defines the Technical Requirements (TRD) for JARVIS OS, establishing the software engineering stacks, database engine specifications, and API protocols.

## Scope
Applies to all backend API developers, frontend UI developers, desktop shell integrators, and security sandbox engineers working on JARVIS OS.

## Technical Stack Specifications

### 1. Backend Core
- **Engine:** Python 3.11+ using FastAPI for asynchronous routing.
- **Task Orchestration:** Custom async queue manager with Redis backplane.
- **WebSocket Gateway:** Real-time bi-directional telemetry streaming to dashboard client.

### 2. Frontend & Desktop Wrap
- **Web App:** Next.js 14+ (React 18, Tailwind CSS, TypeScript).
- **Desktop Shell:** Electron wrapper packaging the FastAPI executable and web bundle into a native client app.
- **Desktop Integration:** Node.js native child-process spawners connecting safely to system CLI APIs.

### 3. Database Layer
- **Relational & Session DB:** PostgreSQL 15+ (relational memory) and Redis 7 (caching, active task queue, and working memory state).
- **Vector Search Engine:** PostgreSQL `pgvector` extension for storing and querying memory embeddings.
- **Graph Store:** NetworkX or RDFlib serialized schema stored inside relational PostgreSQL tables.

### 4. Browser Automation & PC Control
- **Browser automation:** Playwright (Python wrapper) communicating over Chrome DevTools Protocol (CDP).
- **PC Control:** `pyautogui` for mouse/keyboard automation and native Python `subprocess` shell executor with permission guards.

### 5. Sandboxing
- **Local Sandbox:** Docker containers with strictly limited CPU, memory, and read-only host filesystem mounts.

## Responsibilities
- **DevOps Engineer:** Set up PostgreSQL, Redis, and Docker sandboxes.
- **System Architect:** Validate that backend modules maintain asynchronous integrity and do not block the thread pool.

## Dependencies
- Must strictly adhere to the [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md).

## Interfaces
- Backend REST API: `/api/v1/` endpoints.
- WebSocket Stream: `/ws/v1/telemetry`.
- Docker API: Local socket connection `/var/run/docker.sock` (wrapped behind secure access policies).

## Examples
- **Correct Implementation:** Database connection pool is initialized asynchronously using `asyncpg` and shared across FastAPI request loops.
- **Incorrect Implementation:** Running a synchronous `time.sleep()` inside an async FastAPI route. (Violates asynchronous requirement).

## Failure Cases
- **Database Connection Pool Exhaustion:** Rapid agent subtasks spawn too many database queries. *Mitigation:* Connection pool sizes are limited to 20 connections max, and queries use retry logic with exponential backoff (see `38_ERROR_HANDLING_STANDARD.md`).

## Security Considerations
- Raw SQLite is prohibited for production memory storage. PostgreSQL with SSL is required. Redis keyspaces must be password protected.

## Future Extension
- Tech stack upgrades require an updated Architecture Decision Record (ADR) before packages are modified in `package.json` or `requirements.txt`.

## Related Documents
- [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
- [03_PRODUCT_REQUIREMENTS.md](file:///e:/jarvis/docs/03_PRODUCT_REQUIREMENTS.md)
- [05_SYSTEM_ARCHITECTURE.md](file:///e:/jarvis/docs/05_SYSTEM_ARCHITECTURE.md)
- [06_ARCHITECTURE_DECISION_RECORDS.md](file:///e:/jarvis/docs/06_ARCHITECTURE_DECISION_RECORDS.md)
- [28_SANDBOX_POLICY.md](file:///e:/jarvis/docs/28_SANDBOX_POLICY.md)
