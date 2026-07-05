# 95_PHASE_33_PRODUCTION_READINESS_SPECIFICATION.md

## Purpose
This document establishes the architecture specification for **Phase 33: Enterprise Deployment, Operations & Production Readiness**. It defines health management, dynamic preflight checks, graceful shutdown routines, disaster recovery procedures, configuration profiles, and platform management REST API routes.

## Status
**STATUS:** ✅ FROZEN (2026-07-05)
**Authority:** Rank 4 (Phase Specification)
**Dependencies:** Phase 32

---

## 1. Architectural Position

The Enterprise Readiness and Operations layer encapsulates health management, preflight verification, and graceful shutdown boundaries across all system subsystems:

```
                  ┌──────────────────────────────────────────────┐
                  │              Enterprise Platform             │
                  │             Management API Routes            │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │           DeploymentHealthManager            │
                  │    (Startup Checks, Preflight, Liveness)     │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │                 Kernel Loop                  │
                  │       (Graceful Shutdown & Draining)         │
                  └──────────────────────────────────────────────┘
```

---

## 2. Component Contracts

### 2.1 DeploymentHealthManager

```python
class DeploymentHealthManager:
    """Coordinates platform liveness, readiness, dynamic preflight, and disaster recovery validation."""

    def __init__(
        self,
        settings: Any,
        db_manager: Any,
        event_bus: Any,
        vault_manager: Any,
        orchestrator: Any,
        admin_manager: Any,
    ) -> None:
        """Initialize DeploymentHealthManager with system singletons."""

    async def check_liveness(self) -> Dict[str, Any]:
        """Perform shallow health checks ensuring main services are running in memory.
        
        Returns status "healthy" or "degraded".
        """

    async def check_readiness(self) -> Dict[str, Any]:
        """Verify deep database connection and vault decryption state are ready to accept traffic."""

    async def run_preflight_checks(self) -> Dict[str, Any]:
        """Verify DB connection, Redis ping, Vault lock status, disk space, and clock synchronization."""

    async def verify_disaster_recovery(self) -> Dict[str, Any]:
        """Run backup generation, parse validation, and return recovery reports."""
```

---

## 3. REST Endpoint Specifications

All platform operations endpoints are mounted under `/api/v1/platform` and require `"platform.admin"` permission scope (except where specified):

### 3.1 Platform Status
- **Path**: `GET /api/v1/platform/status`
- **Response**: `{ "status": "healthy", "version": "0.1.0", "environment": "production" }`

### 3.2 Readiness Check
- **Path**: `GET /api/v1/platform/readiness`
- **Response**: `{ "status": "ready", "database": "CONNECTED", "vault": "UNLOCKED" }`

### 3.3 Liveness Check
- **Path**: `GET /api/v1/platform/liveness`
- **Response**: `{ "status": "alive" }`

### 3.4 Preflight Validator
- **Path**: `POST /api/v1/platform/preflight`
- **Response**: `{ "status": "PASSED", "checks": { "database": "OK", "redis": "OK", "vault": "UNLOCKED", "disk": "OK" } }`

### 3.5 Deployment Info
- **Path**: `GET /api/v1/platform/deployment`
- **Response**: `{ "environment": "production", "replicas": 3, "storage_driver": "sqlite" }`

---

## 4. Graceful Shutdown & Draining

Graceful shutdown coordinates:
1. **Draining**: Mark API as un-ready to block new requests.
2. **Worker Interruption**: Stop active task dequeues and orchestrators.
3. **Flushing**: Let active jobs finish or persist snapshots.
4. **Closing**: Terminate Redis, database connection pools, and file loggers.

---

## 5. Verification and Acceptance Criteria

- **Platform Status**: Verify liveness and readiness APIs return appropriate codes.
- **Preflight checks**: Verify failing dependency pings return degraded statuses.
- **Graceful Shutdown**: Verify shutdown cleans up threads, tasks, and DB connections cleanly without warnings.
- **Disaster Recovery**: Verify backup creation and restoration flows pass integrity scans.
