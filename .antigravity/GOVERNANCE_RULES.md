# GOVERNANCE RULES

## 1. Authority Hierarchy
When two documentation or code sources conflict, the resolution follows this strict ranking. Higher rank wins. No exceptions.

| Rank | Source | Mutability |
| --- | --- | --- |
| **1 (Highest)** | User Decision / Instruction | Current developer mandate; cannot override Ranks 2–4. |
| **2** | AGENTS.md & System Constitutions | Boot sequence, authority ranking, STOP rules, protocols. |
| **3** | Master Index (`docs/60_MASTER_INDEX.md`) | Document locator. |
| **4** | Phase Specifications (`docs/74` to `docs/80+`) | Complete feature contracts, interfaces, and behaviors. |
| **5** | Implementation Plans | Milestone breakdowns and execution strategy. |
| **6** | Implementation Code | Python modules in `core/` and `api/`. |
| **7 (Lowest)** | Walkthrough history | Historical walkthrough records (`walkthrough.md`). |

---

## 2. Frozen Architecture Boundaries
The following files and components are **FROZEN** and may not be modified without an approved Change Request (CR):
* **Dependency Layer Invariant:** `UI` → `API` → `Brain` → `{Memory, Tools}`. Reversals are blocked.
* **API Contracts:** Outlined in [02_API_CONTRACTS_FREEZE.md](file:///e:/jarvis/docs/architecture/02_API_CONTRACTS_FREEZE.md).
* **Database Schemas:** Outlined in [03_DATABASE_SCHEMAS_FREEZE.md](file:///e:/jarvis/docs/architecture/03_DATABASE_SCHEMAS_FREEZE.md).
* **Component Interfaces:** Outlined in [08_COMPONENT_INTERFACE_FREEZE.md](file:///e:/jarvis/docs/architecture/08_COMPONENT_INTERFACE_FREEZE.md).
* **Phase baselines:** Phase 1–13 (`docs/74` and `docs/75`), Phase 14 (`docs/76`), Phase 15 (`docs/77`), Phase 17 (`docs/78`), Phase 18 (`docs/79`), Phase 19 Spec & Plan (`docs/80` and `docs/81`).

---

## 3. Automatic STOP Protocol
Coding agents must immediately halt and emit a Conflict Report if any of the following occur:
1. A frozen interface or boundary is modified.
2. A circular dependency is detected between layers or modules.
3. A Repository gains validation, planning, business logic, or tool execution.
4. A Compiler gains tool execution or database write responsibility.
5. A Validator writes to the database, executes a tool, or calls an LLM.
6. An Orchestrator bypasses the `ExecutionOrchestrator` or compiles a workflow directly.
7. The API layer imports an implementation detail incorrectly (layer reversal).
8. Two authority sources conflict and cannot be resolved by rank.
9. The approved specification and the existing code disagree.
10. A DTO required by the DTO-First rule does not exist.
11. The implementation plan deviates from or contradicts the approved Phase Specification.

### Conflict Report Format
```
IMPLEMENTATION BLOCKED

Reason:            <one of the 11 conditions above, stated precisely>
Affected files:    <paths>
Conflicting source: <which doc / interface / spec / plan>
Source A (e.g. Spec): <details>
Source B (e.g. Code/Plan): <details>
Impact:            <governance / architectural impact>
Recommended resolution: <your proposal — non-binding>
Authority invoked: <rank from Section 1>

Waiting for architect approval. Not proceeding.
```

---

## 4. Specification-First Rule
When implementation conflicts with an approved frozen specification, the implementation always loses. Do not rewrite a specification to match divergent code on disk. 
To resolve conflicts, you must either:
1. **Archive the divergent implementation** and re-derive from the specification; OR
2. **Propose a Change Request (CR)**, stop coding, and wait for human review.

---

## 5. Change Request (CR) Process
To modify any frozen document, boundary, or specification:
1. **Propose:** Create a `CR-XXX` entry outlining the rationale, files affected, risks, benefits, and specifications affected.
2. **Review:** The Architecture Gatekeeper reviews for Single Responsibility, immutability, and layer compliance.
3. **Approve:** Modification is blocked until explicit human approval is recorded.
4. **Record:** Append the approved CR to the target spec, increment the document version, and execute.
