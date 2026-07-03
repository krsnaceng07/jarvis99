# ARCHITECTURE RULES

## 1. System Layer Hierarchy
The system enforces a strict unidirectional layer hierarchy. Lower layers must never import or depend on higher layers.

```
      UI (Frontend / Console)
                 ↓
      API (FastAPI) / CLI (Click)
                 ↓
     Brain (Orchestrators / Kernels)
                 ↓
    Domain (Retrieval, Retention, Scoring)
                 ↓
Infrastructure (Repositories, DB, Vector Store)
```

---

## 2. Permitted and Forbidden Import Paths

### UI Layer
* **Allowed:** API clients, DTOs.
* **Forbidden:** Brain components, Domain logic, Repositories, Database engines, LLM clients.

### API & CLI Layer
* **Allowed:** Brain Orchestrators, Kernels, DTOs, Validators, Configuration.
* **Forbidden:** Direct Repository imports, scoring engines, database connections, vector stores, prompt compilation logic.
* *Rule:* API/CLI must act as thin serialization adapters. They can only interface with Orchestrators.

### Brain Layer
* **Allowed:** Domain engines, compilers, validators, event buses, repositories, DTOs.
* **Forbidden:** UI code, API endpoints, FastAPI objects, CLI commands.
* *Rule:* Coordinates execution. Must use `ExecutionOrchestrator` for all tool/workflow runs.

### Domain Layer
* **Allowed:** Compilers, validators, repositories, data wrappers, DTOs.
* **Forbidden:** Brain orchestrators, API routes, UI components.
* *Rule:* Pure logical processing (e.g., scoring, retrieval ranking, TTL checks). No external IO or tool execution.

### Infrastructure Layer (Repositories & Adapters)
* **Allowed:** Database connectors, filesystem utilities, DTOs.
* **Forbidden:** Domain engines, Brain orchestrators, API modules.
* *Rule:* Isolated data access. Business logic is strictly prohibited.

---

## 3. Dependency Invariants
* **No Circular Dependencies:** Circular imports between files or directories must be rejected immediately during the quality gate.
* **No Layer Bypassing:** Under no circumstances should the API layer call a repository directly, nor should a repository call a domain ranking engine.
* **DTO-First Ordering:** When building components, implement and freeze the DTO layer first, followed by the Validator, Compiler, Repository, Orchestrator, and finally tests.
* **Single Responsibility Principle (SRP):** Each file must serve one and only one architectural concern. A file like `service.py` cannot contain both SQL queries and LLM prompt templates.
