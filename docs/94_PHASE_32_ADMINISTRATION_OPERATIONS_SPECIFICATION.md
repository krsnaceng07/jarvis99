# 94_PHASE_32_ADMINISTRATION_OPERATIONS_SPECIFICATION.md

## Purpose
This document establishes the architecture specification for **Phase 32: Platform Administration & Operations**. It defines system diagnostics, dynamic configuration live-reloading, backup/restore routines, task run controls, and the dashboard gateway interface for JARVIS OS.

## Status
**STATUS:** ✅ FROZEN (2026-07-05)
**Authority:** Rank 4 (Phase Specification)
**Dependencies:** Phase 31

---

## 1. Architectural Position

The Administration and Operations subsystem exposes a control and diagnostics layer on top of all existing services:

```
                  ┌──────────────────────────────────────────────┐
                  │               Admin Dashboard                │
                  │            (HTML/JS/CSS SPA UI)              │
                  └──────────────────────┬───────────────────────┘
                                         │ HTTP REST API
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │             Admin Routes API                 │
                  │        (Authentication & Authz Gate)         │
                  └──────────────────────┬───────────────────────┘
                                         │
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │                AdminManager                  │
                  │   (Diagnostics, Backup, Config, Controls)    │
                  └──────┬───────────┬───────────┬───────────┬───┘
                         │           │           │           │
                         ▼           ▼           ▼           ▼
                   ┌──────────┐┌───────────┐┌──────────┐┌──────────┐
                   │ Database ││ Event Bus ││  Vault   ││Scheduler │
                   └──────────┘└───────────┘└──────────┘└──────────┘
```

---

## 2. Scope & Boundaries

### In Scope
- **System Health Diagnostics**: Real-time checking of DB session pinging, Redis broker connectivity, Vault status, disk load, CPU, and memory usage.
- **Dynamic Configuration Management**: Ability to view and update system logging levels, synchronization frequencies, and other transient settings dynamically.
- **Backup & Restore Operations**: Atomic serialization of the active database schema/data and system configurations, and restoration from a snapshot backup file.
- **Task Run Controls**: Send signals (`pause`, `resume`, `cancel`, `restart`) to actively running scheduler tasks.
- **Admin API Gateway**: Secure endpoints requiring authenticated access with `"platform.admin"` permission scope.
- **Admin Dashboard UI**: A modern, high-fidelity responsive Single Page Application dashboard.

### Out of Scope
- Orchestration of OS-level processes or VM creation. All controls target the containerized Python runtime.
- Multi-node log aggregation. This phase implements local node log queries only.

---

## 3. Dynamic Configuration & Override Schema

Dynamic configurations override default `Settings` dynamically and are persisted in `dynamic_settings.json`:

```json
{
  "system_log_level": "INFO",
  "sync_interval_seconds": 60,
  "rate_limit_per_minute": 100,
  "telemetry_enabled": true
}
```

---

## 4. Component Contracts

### 4.1 AdminManager

```python
class AdminManager:
    """Manages system diagnostics, dynamic configuration settings, backup/restore routines, and running task controls."""

    def __init__(self, settings: Any, db_manager: Any, event_bus: Any, vault_manager: Any, scheduler: Any) -> None:
        """Initialize AdminManager with DI dependencies."""

    async def get_diagnostics(self) -> Dict[str, Any]:
        """Perform database, redis, vault, and system resource diagnostics checks."""

    async def get_metrics(self) -> Dict[str, Any]:
        """Compile execution counts, cost spent, task success rates, and active run statistics."""

    async def get_dynamic_config(self) -> Dict[str, Any]:
        """Return the current dynamic configuration settings."""

    async def update_dynamic_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Update transient dynamic configurations and write them to dynamic_settings.json."""

    async def control_task(self, task_id: str, action: str) -> bool:
        """Send execution control commands ('pause', 'resume', 'cancel', 'restart') to the running task."""

    async def create_backup(self) -> str:
        """Serialize current database records to backups/db_backup_<timestamp>.json.

        Returns:
            Absolute path of the created backup file.
        """

    async def restore_backup(self, backup_file_name: str) -> bool:
        """Restore database tables and configurations from a backups/ snapshot file."""
```

---

## 5. REST Endpoint Specifications

All admin routes are mounted under `/api/v1/admin` and require `"platform.admin"` permission scope:

### 5.1 System Diagnostics
- **Path**: `GET /api/v1/admin/diagnostics`
- **Response**: `{ "database": "OK", "redis": "OK", "vault": { "initialized": true, "locked": false }, "resources": { "cpu": 12.5, "memory": 42.1 } }`

### 5.2 System Metrics
- **Path**: `GET /api/v1/admin/metrics`
- **Response**: `{ "total_runs": 125, "success_rate": 0.98, "total_cost_usd": 1.24 }`

### 5.3 Dynamic Config
- **Path**: `GET /api/v1/admin/config`
- **Response**: `{ "system_log_level": "INFO", "sync_interval_seconds": 60 }`

### 5.4 Update Config
- **Path**: `POST /api/v1/admin/config/update`
- **Request Body**: `{ "system_log_level": "DEBUG" }`
- **Response**: `{ "status": "SUCCESS", "config": { ... } }`

### 5.5 Task Control
- **Path**: `POST /api/v1/admin/tasks/{task_id}/control`
- **Request Body**: `{ "action": "pause" }`  # pause, resume, cancel, restart
- **Response**: `{ "status": "SUCCESS" }`

### 5.6 Create Backup
- **Path**: `POST /api/v1/admin/backups/create`
- **Response**: `{ "status": "SUCCESS", "backup_file": "db_backup_20260705.json" }`

### 5.7 Restore Backup
- **Path**: `POST /api/v1/admin/backups/restore`
- **Request Body**: `{ "backup_file": "db_backup_20260705.json" }`
- **Response**: `{ "status": "SUCCESS" }`

---

## 6. Verification and Acceptance Criteria

### Automated Test Suite Requirements
- **Diagnostics check**: Assert that the diagnostics API correctly reports connection status of database and cache.
- **Dynamic Config**: Verify that dynamic settings can be modified and that changes are saved to disk and loaded by the system.
- **Backup/Restore integrity**: Generate random data, trigger a backup, delete/modify the data, run restore, and assert that the original data is accurately recovered.
- **Task Controls**: Verify that task signals correctly transition running tasks and cancel active runs.
- **Access Control**: Verify that non-admin requests to all endpoints return 401/403 errors.
