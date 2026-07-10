# ADR-008: JSON-Envelope Multi-Agent Protocol

## Status
* **Status:** Accepted
* **Date:** 2026-07-02
* **Author:** Architecture Team

---

## Context
Solving complex development or operational tasks requires multiple specialized agents (e.g. Planner, Developer, Reviewer, Security) to interact, share logs, and execute task trees dynamically.

---

## Decision
Establish the Multi-Agent communication standard:
* **Protocol Envelope:** Standardized JSON envelopes containing headers (sender_id, receiver_id, correlation_id, timestamp) and typed payload blocks.
* **Message Delivery:** Transport broker (local async queues or Redis Streams) routes messages between active agent sessions.
* **Session Tracking:** The Kernel maintains active agent registries, validating sender authorities and access quotas before routing messages.

---

## Consequences
* **Positive:** Consistent communication structure makes interaction flows fully traceable and debuggable.
* **Negative:** Message parsing overhead; session coordination requires state isolation.

---

## Compliance & Invariants
* All inter-agent message payloads must validate against standard JSON schema envelopes.
* Agents must never bypass the protocol to access another agent's private memory state directly.
