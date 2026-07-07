# 74_PHASE_1_12_MASTER_SPECIFICATION.md

## Purpose
This document establishes the Consolidated Architecture Baseline & Master Specification for JARVIS OS (Phases 1 to 12). It serves as the single source of truth for the frozen system architecture, mapping out interfaces, dependency flows, and security guidelines. Any future changes to these components require a formal Change Request (CR).

## Status
**STATUS: FROZEN**
The architecture defined below is locked. Scope additions or structural changes to reasoning, databases, memory indexing, automation layers, tool orchestration layers, or planning & execution engine loops are blocked without an approved Change Request (CR).

---

## Consolidated System Baseline (Phases 1 to 12)

### 1. Phase 1 to 4: Core Brain & Relational Database Layer
* **Configuration:** Core settings driven by Pydantic config schemas in `core/config.py`.
* **Database Pool:** SQLAlchemy async engine handles transactions and connections in `core/db.py`.
* **Unified Exceptions:** Base exception classes rooted in `JarvisError`, isolating memory, agents, skills, and model providers in `core/exceptions.py`.
* **Persistent Models:** Relational models for sources, chunks, and billing logs defined in `core/memory/models.py`.

### 2. Phase 4.5 & 4.6: Memory, Event Bus, & Vector Store
* **Memory Indexer:** Event-driven worker ([`MemoryIndexer`](file:///e:/jarvis/core/memory/indexer.py#L20)) listens to memory events (`memory.chunk.created` / `deleted`) and populates indices.
* **Vector Index:** Maps text blocks to high-dimensional embeddings using pgvector.
* **Knowledge Graph:** Node-edge relational concepts mapped to the graph DB schema.
* **Telemetry & Event Bus:** Structured JSON communication protocols over the local Redis event stream (`core/events/redis_bus.py`).

### 3. Phase 5: Reasoning, Planning, & Cost Governance
* **Http Transport Abstraction:** [`IHttpTransport`](file:///e:/jarvis/core/reasoning/transport.py#L22) decouples vendor clients from direct network libraries, implemented via [`UrllibTransport`](file:///e:/jarvis/core/reasoning/transport.py#L50).
* **Provider Config DTO:** [`ProviderConfig`](file:///e:/jarvis/core/reasoning/provider.py#L32) DTO manages model parameters, timeouts, and token limit constraints.
* **Credential Manager:** [`CredentialManager`](file:///e:/jarvis/core/reasoning/credentials.py#L10) securely isolates API keys.
* **Model Capability Registry:** [`ModelCapabilityRegistry`](file:///e:/jarvis/core/reasoning/registry.py#L11) ranks suitability scores (0-100) per task category (Planning, Coding, etc.).
* **Budget Governance:** [`CostGovernor`](file:///e:/jarvis/core/reasoning/cost.py#L19) maintains `Decimal` calculations, checking daily, monthly, and per-call budgets against database billing records using a 30-second TTL in-memory spending cache.
* **Budget-Aware Router:** [`ModelRouter`](file:///e:/jarvis/core/reasoning/router.py#L18) filters external models and redirects queries to local models (Qwen, Llama) when the daily budget is exhausted. Contains retry logic and rate limit filters.
* **Rate Limiter:** [`ProviderRateLimiter`](file:///e:/jarvis/core/reasoning/rate_limiter.py#L12) monitors RPM, TPM, and concurrency sliding windows.
* **Health Monitor:** [`ProviderHealthMonitor`](file:///e:/jarvis/core/reasoning/health_monitor.py#L12) executes background ping validation checks to manage circuit breaker states.

### 4. Phase 6 & 7: PC Controller & Browser Automation
* **PC Automation:** PyAutoGUI adapter coordinate translations and permission gates in `pc/controller.py`.
* **Custom Browser Client:** Playwright Chromium CDP integration driving web scrapes, dashboard WebSocket streams, and soft profile sandboxes.

### 5. Phase 8 & 9: Subagent Swarms & Learning Engines
* **Multi-Agent Protocol:** Subagent lifecycle managers, queues, and locks orchestration in `core/runtime`.
* **Learning Engine:** Scrapers, extractors, and summarizers parsing documentation to ingest new skills in `core/learning`.
* **Security & Docker Sandbox:** Dynamic container sandboxing in `core/runtime/container_driver.py` preventing unauthorized local directory mounts and execution.

### 6. Phase 11: Decoupled Tool Orchestration
* **Topological DAG Scheduler:** [`DependencyResolver`](file:///e:/jarvis/core/tools/dependency_resolver.py#L14) validates execution waves, builds task-dependency layers, and detects circular import cycles.
* **Wave Executor:** [`WaveExecutor`](file:///e:/jarvis/core/tools/wave_executor.py#L27) coordinates parallel task execution driven by sync events, enforcing a global semaphore-based limit of 5 concurrent subagent operations.
* **Task Retry Engine:** [`RetryManager`](file:///e:/jarvis/core/tools/retry_manager.py#L14) wraps task execution with customizable retry policies and exponential backoffs.
* **Output Consolidation & Aggregation:** [`WaveResultAggregator`](file:///e:/jarvis/core/tools/result_aggregator.py#L14) merges durations, exit codes, output streams, and tool trace logs into a consolidated wave status DTO.
* **Telemetry & Approval Gates:** Integration with `EventBus` to notify status topics (`tool.spawn.started`, `tool.running`, `tool.completed`, `tool.failed`, `tool.retry`, `tool.approval.waiting`). Blocks execution on L2/L3 permissions for human gatekeeper clearance.
* **Idempotency Registry:** Prevents redundant tool calls by checking `idempotency_key` cache and returning previously succeeded outputs.
* **Observability Telemetry:** [`ExecutionMetricsCollector`](file:///e:/jarvis/core/tools/metrics_collector.py#L12) gathers detailed statistics on latency, approval waits, and failure rates.

### 7. Phase 12: Planning & Execution Engine
* **Session State Machine:** Formalized execution lifecycle states (`Planning`, `Executing`, `Reflecting`, `Repairing`, `Completed`, `Failed`, `Cancelled`).
* **Planning Service (`PlanningService`):** [`PlanningService`](file:///e:/jarvis/core/reasoning/planning_service.py) coordinates prompt building and routing to return Pydantic `ExecutionPlan` DTOs.
* **Plan Version Manager (`PlanVersionManager`):** [`PlanVersionManager`](file:///e:/jarvis/core/reasoning/plan_version_manager.py) manages serialization snapshots, rollbacks, and computes structural task changes diff logs between plan versions.
* **Reasoning Execution Engine (`ReasoningExecutionEngine`):** [`ReasoningExecutionEngine`](file:///e:/jarvis/core/reasoning/engine.py) manages the execution loop, budget checkpoints (boundaries 1-5), wave execution runs, and self-reflection recovery paths.
* **Telemetry & Telemetry Enums:** Emits state transition event broadcasts (`engine.state.transition`) correlating records across execution stages with a unified `trace_id`.

---

## Core Abstraction Flow
The reasoning, planning waves, and call routing layers strictly adhere to the following dependency hierarchy:

```
[ReasoningExecutionEngine] ──> [PlanningService] ──> [ModelRouter] ──> [IModelProvider]
             │                       │
             ├──> [PlanVersionMgr]   └──> [PromptBuilder]
             └──> [ExecutionOrchestrator] ──> [WaveExecutor] ──> [ToolRuntime]
```

---

## Future Change Control Process (CR)
To modify components under this baseline, a formal Change Request (CR) must be proposed:
1. **Change Proposal:** Declare name `CR-XXX`, reasoning, files affected, risks, and benefits.
2. **Review:** Gatekeeper reviews for architectural consistency, safety, and scalability.
3. **Approval:** Lock is updated only after explicit human Gatekeeper approval.

---

## Related Documents
* [00_PROJECT_CONSTITUTION.md](file:///e:/jarvis/docs/00_PROJECT_CONSTITUTION.md)
* [57_IMPLEMENTATION_ROADMAP.md](file:///e:/jarvis/docs/57_IMPLEMENTATION_ROADMAP.md)
* [58_PHASE_BUILD_ORDER.md](file:///e:/jarvis/docs/58_PHASE_BUILD_ORDER.md)
* [60_MASTER_INDEX.md](file:///e:/jarvis/docs/60_MASTER_INDEX.md)
