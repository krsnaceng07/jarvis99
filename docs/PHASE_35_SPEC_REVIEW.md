# Phase 35 Specification Review (DRAFT)

This document contains the structural review and gap analysis of [97_PHASE_35_DISTRIBUTED_SCALE_SPECIFICATION.md](file:///e:/jarvis/docs/97_PHASE_35_DISTRIBUTED_SCALE_SPECIFICATION.md). It outlines critical architectural omissions (gaps), ambiguities, cross-phase alignment checks, and recommendations categorized into **blocking** and **non-blocking** items.

---

## 1. Governance Context

- **Authority Level:** Rank 4 (Phase Specification Review)
- **Target Spec:** [97_PHASE_35_DISTRIBUTED_SCALE_SPECIFICATION.md](file:///e:/jarvis/docs/97_PHASE_35_DISTRIBUTED_SCALE_SPECIFICATION.md)
- **Key Constraints:**
  - Must strictly preserve frozen interface files under **Phase 31** (specifically [federation.py](file:///e:/jarvis/core/runtime/federation.py) and [federation.py](file:///e:/jarvis/api/routes/federation.py)).
  - Implementation must follow **Option B (Additive-only Architecture)**.

---

## 2. Blocking Gaps (Must be resolved before Approval)

### Gap 2.1: Lack of Load Caching Mechanism & Stale Balancing Decisions
- **Problem:** Section 3.3 defines `GET /api/v1/federation/load` to fetch current load metrics, but does not define caching requirements. Querying load metrics (CPU, RAM, active tasks) on every routing decision introduces high latency and can trigger request storms.
- **Architect Directive:** A metrics cache must be added to the peer selector with a **2–3 second Time-to-Live (TTL)**. A TTL of 5 seconds is rejected by the architect to prevent stale load balancing decisions in rapidly changing clusters, whereas a 2-3 second TTL balances freshness with API efficiency.
- **Resolution:** `ScaleManager` must store load reports in an memory cache mapped with a maximum 3-second freshness window.

### Gap 2.2: Task Result Retrieval Lifecycle for Asynchronous Offloads
- **Problem:** Section 3.1 specifies that `POST /api/v1/federation/offload` returns status `QUEUED`, a `task_id`, and `node_id`. However, the specification is completely silent on how the initiator node retrieves execution results (stdout, stderr, exit code, or return values) once the worker node completes the task.
- **Resolution:** Establish a clear protocol contract.
  - **Required Route Addition:** Specify a new callback endpoint `/api/v1/federation/offload/callback` where worker nodes post signed execution receipts back to the initiator.
  - **Alternative/Fallback Route:** Expose a polling endpoint `GET /api/v1/federation/offload/{task_id}/result` protected by the custom peer signature validation middleware.

### Gap 2.3: Security Boundary & Whitelisting for Remote Tool Execution
- **Problem:** Endpoint `POST /api/v1/federation/tools/execute` delegates tool execution. Allowing remote execution of generic tools represents a major safety and security risk.
- **Resolution:** The specification must enforce a strict remote tool execution boundary:
  - Only specific sandboxed tools (e.g., `python_sandbox`) may be executed.
  - Destructive tools, shell access tools (`shell_runtime`), or direct host commands must be rejected by the worker.
  - A strict whitelist configuration must be verified at the endpoint level.

---

## 3. Non-Blocking Recommendations (Quality/Maintenance Improvements)

### Recommendation 3.1: Deterministic Load-Balancing Logic (Tie-Breaking)
- **Problem:** The spec requests "lowest-load selection" but does not define behavior if multiple peer nodes report identical load metrics.
- **Recommendation:** Implement a deterministic tie-breaker, sorting peer list alphabetically by `node_id` when load metrics are equal. This ensures predictability in automated test configurations.

### Recommendation 3.2: Replay Attack Protection Integration
- **Problem:** Replay attack checking is done at the signature layer, but the spec does not explicitly confirm if Phase 35 routes reuse Phase 31 validation.
- **Recommendation:** Enforce that all new endpoints mount `verify_federation_signature` directly as a route dependency. This guarantees reuse of HMAC validation, message freshness checking, and nonce replay cache without duplicating logic.

### Recommendation 3.3: Offload Task Payload Context Schema
- **Problem:** The JSON body payload for task offloading `{ "task_id": "...", "type": "execute_code", "payload": { "code": "..." } }` lacks environment configuration, variables, or timeout limits.
- **Recommendation:** Add optional `timeout_seconds` and `env_vars` fields to the offload payload schema to provide better isolation and control.
