# ENGINEERING CONSTITUTION

## The 10 Golden Rules

### Golden Rule 1: Never Violate Frozen Specifications
Specifications (Rank 4) are absolute. If implementation details conflict with the specification, the implementation loses. You must **STOP** immediately and request or propose a Change Request (CR) or Architecture Decision Record (ADR).

### Golden Rule 2: Never Invent Architecture
Architecture and interfaces come only from frozen specifications, approved ADRs, and authorized implementation plans. Never introduce new component structures, layer interfaces, or orchestration flows from assumptions.

### Golden Rule 3: Execution Order Priority
Every implementation must satisfy this order:
```
Architecture
     ↓
  Security
     ↓
Reliability
     ↓
  Testing
     ↓
Documentation
     ↓
   Code
```
Never reverse this order. Do not write code before the architecture, security, and verification paths are defined.

### Golden Rule 4: Single Responsibility Principle (SRP)
Every component, module, class, and function has exactly one responsibility. If a module orchestrates, it must not execute tools. If it validates, it must not write to a database.

### Golden Rule 5: No Business Logic in Adapters & Repositories
No business, planning, compilation, or execution logic may live inside:
* **Repository:** Restricted to CRUD, database transactions, version tracking, and checksum validation.
* **API / CLI:** Restricted to thin serialization, HTTP routing, schema conversion, and input handoff to the orchestrator.
* **DTO:** Restricted to strict, immutable data contract definitions (Pydantic models).
* **Config:** Restricted to loading, profile management, and environment parsing.

### Golden Rule 6: Everything Behind Interfaces
All core services and interactions must depend on abstract interfaces, enabling modular swapping, mock-testing, and interface-driven development.

### Golden Rule 7: No Hidden State
All system state, parameters, and inputs must be passed explicitly. Global variables, hidden module-level caches, or un-tracked state objects are prohibited.

### Golden Rule 8: Explicit Failure
All errors, exceptions, and system failures must be caught, wrapped, and propagated explicitly. Silently ignoring errors (`except: pass` or unlogged try/catch blocks) is forbidden.

### Golden Rule 9: Documentation Obligation
Every public API, function signature, DTO field, and class must be fully documented with clear docstrings, parameter descriptions, types, and return values.

### Golden Rule 10: No Temporary Solutions
No placeholders, stub responses, mock returns in production files, or "TODO" items. Every line written must be production-ready and fully implemented.

---

## Component Level Invariants

| Component Type | Permitted Responsibilities | Forbidden Responsibilities |
| --- | --- | --- |
| **DTO** | Pydantic data schemas, field defaults, deserialization validation. | Database IO, business calculations, network requests, validation logic. |
| **Validator** | Visibility, bounds, and contract constraint checking. | Writing to databases, calling external APIs, executing tools, calling LLMs. |
| **Compiler** | Workflow and node transformation, schema mapping. | Executing workflows, triggering tools, database writes. |
| **Repository** | CRUD, version tracking, checksum verification, database transactions. | Business calculations, API calls, planning, orchestrating workflow steps. |
| **Orchestrator** | Event orchestration, coordination between repository and engines. | Direct database writes, direct workflow compilation, tool execution logic. |
| **Kernel** | Main runtime loop, task scheduler interface. | API routing, direct DB operations, business logic. |

---

## Core Engineering Reflection
Before writing code, answer:
1. *Can another engineer read and immediately understand this design?*
2. *Can this scale under stress or load?*
3. *Can this system recover from network, database, or API failures?*
4. *Can this component be isolated and easily replaced or mocked?*
5. *Can this be fully validated with automated unit tests?*
6. *Can this logic be observed via standard telemetry or tracing?*
7. *Can it fail safely without compromising security or data integrity?*

Only when the answer to all of these is a clean **YES** may implementation begin.
