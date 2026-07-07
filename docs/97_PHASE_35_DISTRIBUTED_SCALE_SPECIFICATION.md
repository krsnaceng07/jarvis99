# 97_PHASE_35_DISTRIBUTED_SCALE_SPECIFICATION.md

## Purpose
This document establishes the architecture specification for **Phase 35: Distributed Task Offloading & Remote Tool Execution**. It defines the protocols, interfaces, and security contracts allowing federated JARVIS nodes to offload swarm tasks and execute sandboxed tools remotely over cryptographically signed peer connections.

## Status
**STATUS:** ✅ FROZEN (2026-07-05, 1132 tests passed)
**Authority:** Rank 4 (Phase Specification)
**Dependencies:** Phase 34

---

## 1. Architectural Position

Phase 35 extends the federation layer (Phase 31) to support distributed compute and remote environment access:

```
    Node A (Local Initiator)                           Node B (Remote Worker)
┌───────────────────────────┐                       ┌───────────────────────────┐
│     SwarmOrchestrator     │                       │                           │
│  (Seeks remote execution) │                       │                           │
│            │              │                       │                           │
│            ▼              │   HTTP POST Offload   │    Federation API Route   │
│    FederationManager      ├──────────────────────>│   (Authenticates request) │
│ (HMAC signs task payload) │                       │            │              │
│            │              │                       │            ▼              │
│            │              │                       │    Local Swarm Engine    │
│            │              │                       │ (Executes sandbox/browser)│
└───────────────────────────┘                       └───────────────────────────┘
```

---

## 2. Component Contracts

### 2.1 ScaleManager

A new service coordinating load assessment, peer selection, task offloading, and remote tool delegation.

```python
class ScaleManager:
    """Coordinates remote task offloading and distributed tool execution across federated peers."""

    def __init__(
        self,
        settings: Any,
        db_manager: Any,
        federation_manager: Any,
        vault_manager: Any,
        local_orchestrator: Any,
        local_sandbox: Optional[Any] = None,
    ) -> None:
        """Initialize ScaleManager with system dependencies."""

    async def offload_task(self, peer_node_id: str, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Sign and offload a task payload to a federated peer for remote execution.

        Returns:
            Remote task execution receipt and status.
        """

    async def execute_remote_tool(
        self, peer_node_id: str, tool_name: str, arguments: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Delegate a tool execution request (e.g. sandbox code run) to a remote peer.

        Returns:
            The tool execution result payload.
        """

    async def get_node_load_metrics(self) -> Dict[str, Any]:
        """Calculate local load factors (CPU, memory, active task count) for load balancing."""
```

---

## 3. REST Endpoint Specifications

All endpoints are mounted under `/api/v1/federation` and are protected using the P2P request signature validation middleware:

### 3.1 Inbound Task Offload
- **Path**: `POST /api/v1/federation/offload`
- **Security**: Requires a valid P2P HMAC signature.
- **Request Body**: `{ "task_id": "...", "type": "execute_code", "payload": { "code": "..." } }`
- **Response**: `{ "status": "QUEUED", "task_id": "...", "node_id": "..." }`

### 3.2 Inbound Remote Tool Execution
- **Path**: `POST /api/v1/federation/tools/execute`
- **Security**: Requires a valid P2P HMAC signature.
- **Request Body**: `{ "tool_name": "python_sandbox", "arguments": { "code": "..." } }`
- **Response**: `{ "success": true, "stdout": "...", "stderr": "" }`

### 3.3 Node Load Status
- **Path**: `GET /api/v1/federation/load`
- **Security**: Requires a valid P2P HMAC signature or platform administrator permissions.
- **Response**: `{ "cpu_usage": 0.45, "memory_usage": 0.60, "active_tasks": 2 }`

---

## 4. Security & Isolation Invariants
- **Authentication**: All remote execution requests must pass cryptographically validated HMAC-SHA256 handshakes matching the P2P federation secrets.
- **Sandboxing**: Any code execution offloaded to a peer node must be routed strictly through the local Docker Sandbox container runtime, preventing remote commands from affecting the host.

---

## 5. Verification and Acceptance Criteria
- **Secure handshake**: Verify offloading requests carrying invalid or tampered signatures are rejected.
- **Remote Tool Delegation**: Verify Node A can call Playwright/Python tool actions on Node B and receive exact results.
- **Load Balancing**: Verify Node A selects the peer node carrying the lowest load metrics for execution.
