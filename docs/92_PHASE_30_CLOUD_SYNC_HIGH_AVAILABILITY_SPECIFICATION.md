# 92_PHASE_30_CLOUD_SYNC_HIGH_AVAILABILITY_SPECIFICATION.md

## Purpose
This document establishes the architecture specification for **Phase 30: Cloud Sync & High Availability**. It implements encrypted synchronization pipelines for local vault secrets and memory snapshots, conflict resolution algorithms (Last-Write-Wins / Vector Clocks), high-availability replication protocols for persistent databases, and corresponding REST routes.

## Status
**STATUS:** FROZEN (2026-07-04 | 1080 passed)
**Authority:** Rank 4 (Phase Specification)
**Dependencies:** Phase 29

---

## 1. Architectural Position

Phase 30 introduces cloud synchronization and HA replication layers beneath the database and security layers:

```
        Client Request (REST Sync)
                     │
                     ▼
          FastAPI Router (/api/v1/sync/*)
       ┌────────────────────────────────────────────────────────┐
       │ Requires permission: "platform.admin"                  │
       └─────────────────────┬──────────────────────────────────┘
                             │
                             ▼
                     Sync Orchestrator
       ┌────────────────────────────────────────────────────────┐
       │ - Encrypts local state (Vault / Memory)                │
       │ - Evaluates conflict resolution (LWW / Vector Clock)    │
       └─────────────────────┬──────────────────┬───────────────┘
                             │                  │
                             ▼                  ▼
                       Cloud Storage       Replica DB (HA)
       ┌───────────────────────────┐      ┌─────────────────────┐
       │ S3 / GCS / Mock Storage   │      │ Active-Passive Sync │
       └───────────────────────────┘      └─────────────────────┘
```

---

## 2. Scope & Boundaries

### In Scope
- **Encrypted Sync Pipeline**: Sync local vault (`secrets/vault.enc`) and memory snapshots to a remote/cloud bucket (or mock endpoint) encrypted using client-side AES-256-GCM.
- **Conflict Resolution (LWW / Vector Clock)**: Address concurrent mutations using a Last-Write-Wins timestamp comparator or a Vector Clock matrix to determine version precedence.
- **HA Database Replication**: Support active-passive failover and replication protocols for SQLite memory storage, ensuring read-only secondary replica nodes can be brought active on primary failure.
- **Sync Endpoints**: Introduce `/api/v1/sync/push`, `/api/v1/sync/pull`, and `/api/v1/sync/status` REST routes protected by `"platform.admin"` permission.

---

## 3. Data Sync & Conflict Resolution Schema

### 3.1 Metadata Header
Sync payloads exported to the cloud contain a sync header detailing node versioning:
```json
{
  "client_id": "node_uuid_123",
  "vector_clock": {
    "node_uuid_123": 4,
    "node_uuid_456": 2
  },
  "timestamp": "2026-07-04T23:00:00Z",
  "payload": "base64_encoded_nonce_ciphertext_tag_blob..."
}
```

### 3.2 Conflict Resolution Policies
1. **Vector Clock Dominance**: If vector clock $V_A > V_B$ (dominates in all positions), version $A$ is automatically merged.
2. **Concurrent Conflict (Fallback to LWW)**: If clocks are concurrent (independent updates on different nodes), the engine resolves via Last-Write-Wins (LWW) using the `timestamp` field.

---

## 4. Component Contracts

### 4.1 SyncManager

```python
class SyncManager:
    """Orchestrates client-side encryption, version clock tracking, and cloud sync push/pull."""

    def __init__(self, vault_manager: Any, storage_client: Any, event_bus: Optional[Any] = None) -> None:
        """Initialize SyncManager with local vault and cloud storage adapter."""

    async def push_state(self) -> Dict[str, Any]:
        """Encrypt local state and push to cloud, resolving locks.

        Returns:
            Sync status metadata.
        """

    async def pull_state(self) -> Dict[str, Any]:
        """Pull remote state, run conflict resolution, and update local state atomically.

        Returns:
            Resolution status metadata.
        """
```

---

## 5. Security & Auth Middleware Integration

### 5.1 Admin Endpoints
Introduce routes in `api/routes/sync.py` protected by `"platform.admin"` permission:
- `POST /api/v1/sync/push` -> Trigger state push.
- `POST /api/v1/sync/pull` -> Trigger state pull.
- `GET /api/v1/sync/status` -> Retrieve sync logs.

---

## 6. Verification and Acceptance Criteria

### Automated Test Suite Requirements
- **Encrypted sync round-trip**: Push state, verify payload on mock storage is fully encrypted, pull it on a clean node, and verify decryption succeeds.
- **Conflict resolution**: Mock concurrent updates with diverging vector clocks and timestamps, and verify the LWW/Vector clock logic resolves to the correct dominant state.
- **HA database replication**: Simulate primary database failures, trigger replica node upgrade, and verify read-write availability.
- **API security**: Verify sync routes reject clients lacking `"platform.admin"` permission scope.
