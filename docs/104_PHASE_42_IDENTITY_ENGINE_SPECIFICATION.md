# 104_PHASE_42_IDENTITY_ENGINE_SPECIFICATION.md

## Status
**STATUS:** FROZEN (2026-07-06)
**Authority:** Rank 4 (Phase Specification)
**Dependencies:** Phase 41 (Capability Registry & Skill Runtime)
**Date:** 2026-07-06

---

## 1. Problem Statement

JARVIS OS executes autonomous loops via the `AgentLoop`. However, the agent's core identity—such as name, persona, system prompt instructions, temperature, model provider, and model name—is either hardcoded or statically configured. 

Phase 42 introduces the **Identity Engine**. This component provides a database-backed, version-controlled, dynamically switchable identity management system. The agent loops can run under different personas (e.g. "Software Engineer", "Research Analyst", "System Auditor") with distinct system prompts, token budgets, temperature settings, and model routing targets, configurable at runtime via API endpoints.

---

## 2. Architecture & Design

```text
       [ API / Client ]
              │
              ▼ (REST calls)
      ===============================
             IDENTITY SERVICE
      ===============================
              │
              ├─ [Database Registry: AgentIdentityModel]
              └─ [Active Identity Cache]
              │
              ▼ (Injects system prompt & config)
      ===============================
         LLM RUNTIME / PROMPT BUILDER
      ===============================
```

---

## 3. Directory Layout

The Identity Engine components will be organized as follows:

```text
core/reasoning/
  ├── identity.py             # AgentIdentity DTO, ORM Model, and Service
  ├── identity_repository.py  # Database CRUD for agent identity records
api/routes/
  └── identity.py             # REST API endpoint handlers
```

---

## 4. Key Invariants

| # | Invariant |
|---|-----------|
| IE-1 | **Single Active Identity**: There must be exactly one active identity marked as `is_active=True` in the database. Activating a new identity must automatically deactivate all others. |
| IE-2 | **Fallback Identity**: If no identity records exist in the database, the engine must dynamically load and use a hardcoded default identity (e.g., "JARVIS Agent" default persona) to prevent system failure. |
| IE-3 | **Immutable Core Schemas**: The active identity details (system prompt, temperature, provider, model) must not change mid-execution loop for a running session. |

---

## 5. Data Schemas

### Database Schema (`agent_identities`)
* `id`: `Uuid`, Primary Key
* `name`: `String(100)`, Unique, Not Null (e.g., "Developer Agent")
* `role`: `String(100)`, Not Null (e.g., "developer")
* `system_prompt`: `Text`, Not Null
* `temperature`: `Float`, Default `0.0`
* `model_provider`: `String(50)`, Default "openai"
* `model_name`: `String(100)`, Default "gpt-4o"
* `is_active`: `Boolean`, Default `False`
* `created_at`: `DateTime`
* `updated_at`: `DateTime`

### REST API Contracts

#### `GET /api/v1/identities`
* Returns: `200 OK` with lists of all configured identities.

#### `POST /api/v1/identities`
* Accepts: JSON body with `name`, `role`, `system_prompt`, `temperature`, `model_provider`, `model_name`.
* Returns: `201 Created` on successful validation and insertion.

#### `POST /api/v1/identities/{id}/activate`
* Returns: `200 OK` after atomically setting target identity as active and other records as inactive.

---

## 6. Verification Plan

- **Automatic Fallback Verification**: Delete all identities and verify the system defaults back to a hardcoded baseline prompt.
- **Uniqueness / Active Lock Verification**: Activate an identity and verify that all other database records are automatically marked inactive.
- **Prompt Injection Verification**: Run a test LLM call without specifying a system prompt, and verify that the active identity's system prompt is correctly loaded and appended.
- **REST Validation**: Verify that the endpoints respond with standardized JSON envelopes.
