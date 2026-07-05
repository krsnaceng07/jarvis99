# 93_PHASE_31_FEDERATION_SPECIFICATION.md

## Purpose
This document establishes the architecture specification for **Phase 31: Platform Scale & Federation**. It defines the federated multi-node orchestration capabilities of JARVIS OS, enabling independent nodes to register peers, authenticate inter-node messages via cryptographically secure HMAC signatures, route tasks across nodes, and monitor peer health.

## Status
**STATUS:** FROZEN (2026-07-05)
**Test Count at Freeze:** 1086 passed
**Authority:** Rank 4 (Phase Specification)
**Dependencies:** Phase 30

---

## 1. Architectural Position

Phase 31 introduces a peer-to-peer federation layer extending the multi-agent routing capabilities to remote nodes:

```
    Node A (Local Client)                           Node B (Remote Peer)
┌───────────────────────────┐                   ┌───────────────────────────┐
│     Agent executing       │                   │                           │
│            │              │                   │                           │
│            ▼              │                   │                           │
│    FederationManager      │  HTTP POST Route  │    Federation Route API   │
│ (HMAC signs payload)  ────┼───────────────────┼──> (Verifies signature)   │
│            │              │   (AES Encrypted) │            │              │
│            ▼              │                   │            ▼              │
│   Federation Database     │                   │     Local Swarm Bus       │
└───────────────────────────┘                   └───────────────────────────┘
```

---

## 2. Scope & Boundaries

### In Scope
- **Peer Node Registry**: Maintain a list of known federated peers (`node_id`, `base_url`, and status) in a dedicated federation database table or configuration list.
- **HMAC Request Signatures**: Cryptographically verify inter-node requests using HMAC-SHA256 over the payload body and timestamp, with a shared federation secret from the vault to protect against tampering and replay attacks.
- **Federated Message Routing**: Proxy `InterAgentMessage` payloads to remote peer endpoints when the `receiver` node points to a remote peer.
- **Federation Gateway REST Routes**: Expose admin routes `/api/v1/federation/route`, `/api/v1/federation/peers/register`, `/api/v1/federation/peers`, and `/api/v1/federation/peers/{node_id}/health`.
- **Peer Health Monitoring**: Perform active ping check heartbeats querying performance metrics (e.g. latency, load).

### Out of Scope
- Dynamic DHT discovery overlays (e.g., Kademlia). Nodes are registered statically by platform administrators.
- Automatic routing across multiple intermediate hops. Only direct point-to-point routing is supported.

---

## 3. Cryptographic Signature & Envelope Schema

### 3.1 HTTP Signature Header
All inter-node federation requests must contain the following headers:
- `X-Jarvis-Node-Id`: The sender node's ID.
- `X-Jarvis-Signature`: The computed HMAC-SHA256 signature.
- `X-Jarvis-Timestamp`: The ISO-8601 UTC timestamp of the request.

The signature is computed as:
$$Signature = HMAC\_SHA256(Secret, NodeId + Timestamp + RequestBodyString)$$

Nodes must reject any request where:
- The timestamp is older than 5 minutes (preventing replay attacks).
- The signature is invalid.

---

## 4. Component Contracts

### 4.1 FederationManager

```python
class FederationManager:
    """Orchestrates peer registration, signature generation/verification, and federated message routing."""

    def __init__(self, settings: Any, vault_manager: Any, event_bus: Optional[Any] = None) -> None:
        """Initialize FederationManager with settings and vault dependencies."""

    async def register_peer(self, node_id: str, base_url: str) -> Dict[str, Any]:
        """Save peer node credentials and endpoint URL to registry.

        Returns:
            Peer record details.
        """

    async def verify_signature(self, sender_node_id: str, signature: str, timestamp: str, body_bytes: bytes) -> bool:
        """Validate request timestamp and signature using P2P shared secret key."""

    async def route_message(self, peer_node_id: str, message: Any) -> bool:
        """Sign and route an InterAgentMessage to the target peer node URL."""

    async def ping_peer(self, peer_node_id: str) -> Dict[str, Any]:
        """Perform HTTP status check and latency measurement on target peer node."""
```

---

## 5. REST Endpoint Specifications

The following endpoints are hosted in `api/routes/federation.py` and mounted under `/api/v1`:

### 5.1 Route Inbound Agent Message
- **Path**: `POST /api/v1/federation/route`
- **Security**: Handled by custom peer signature validator dependency.
- **Request Body**: `InterAgentMessage` (Pydantic DTO).
- **Behavior**: Verifies headers, then publishes the message locally to the event bus for local agents.

### 5.2 Admin Register Peer
- **Path**: `POST /api/v1/federation/peers/register`
- **Security**: Requires `"platform.admin"` permission scope.
- **Request Body**: `{"node_id": "string", "base_url": "string"}`.
- **Behavior**: Stores peer node metadata.

### 5.3 Admin List Peers
- **Path**: `GET /api/v1/federation/peers`
- **Security**: Requires `"platform.admin"` permission scope.
- **Response**: List of registered peers and cached health metrics.

---

## 6. Verification and Acceptance Criteria

### Automated Test Suite Requirements
- **HMAC verification**: Assert that requests carrying correct HMAC signatures and valid timestamps are accepted, and tampered payloads or expired timestamps are rejected.
- **Inbound routing**: Verify that incoming federated messages are successfully validated and published to the local event bus.
- **Outbound routing**: Mock remote peer node endpoints and assert that outbound messages are signed and posted correctly.
- **Peer registry**: Assert that only administrators carrying `"platform.admin"` permission scope can register and inspect peers.
