# ADR-001: EventBus Architecture & Message Schemas

## Status
* **Status:** Accepted
* **Date:** 2026-07-02
* **Author:** Architecture Team

---

## Context
JARVIS OS requires loose coupling between system layers (UI, API, Brain, memory, tools). Subsystems must be notified of events (e.g., memory updates, skill runs, execution outcomes) asynchronously without creating circular dependency imports or blocking synchronous transaction threads.

---

## Decision
Implement an event-driven publish-subscribe system (`EventBus`) with strict topic schemas.
* **Topics:** Standardized dot-notation namespace paths (e.g., `memory.created`, `memory.deleted`, `skill.executed`).
* **Message Envelope:** Unified JSON payloads specifying timestamp, trace_id, publisher_role, and payload content.
* **Storage Backend:** In-process broker for local lightweight dispatching, moving to Redis streams for multi-process distributed systems.

---

## Consequences
* **Positive:** Decouples core components completely; simplifies extension for future listeners.
* **Negative:** Event delivery is asynchronous, requiring event correlation IDs (e.g., `trace_id`) and handlers to debug event flow traces.

---

## Compliance & Invariants
* All published events must validate against pydantic event DTOs.
* Circular imports between publisher and subscriber modules must be prevented.
