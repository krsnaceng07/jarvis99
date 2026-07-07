# 105_PHASE_43_GOAL_ENGINE_SPECIFICATION.md

## Status
**STATUS:** FROZEN (2026-07-06)
**Authority:** Rank 4 (Phase Specification)
**Dependencies:** Phase 42 (Identity Engine)
**Date:** 2026-07-06

---

## 1. Problem Statement

JARVIS OS needs a robust persistent Goal Engine that enables the system to create, update, prioritize, list, and delete goals/objectives across runs. This persistent framework is essential for maintaining cognitive continuity, tracking goal progress (0–100%), scoping goals to specific identities, managing parent-child goal relationships, and triggering actions when goals change status.

---

## 2. Architecture & Design

```text
       [ API / Client ]
              │
              ▼ (REST calls)
      ===============================
               GOAL SERVICE
      ===============================
              │
              ├─ [Database Registry: AgentGoalModel]
              └─ [Event Bus Publisher]
```

---

## 3. Directory Layout

The Goal Engine components are organized as follows:

```text
core/reasoning/
  ├── goal.py                 # PersistentGoal DTO, GoalStatus, and GoalService
  ├── goal_repository.py      # Database CRUD for agent goals
api/routes/
  └── goal.py                 # REST API endpoints (/api/v1/goals)
```

---

## 4. Key Invariants

| # | Invariant |
|---|-----------|
| GE-1 | **Strict Persistence**: All goal creations, updates, progress changes, and state transitions must be flushed directly to the database. |
| GE-2 | **Clean Layer Separation**: GoalRepository is restricted to CRUD + query filters only. No business logic, validation, event dispatch, or other cognitive processes reside here. |
| GE-3 | **Progress-Lifecycle Bound**: When progress reaches 100%, the goal must automatically transition to `completed` and set its `completed_at` timestamp. |

---

## 5. Data Schemas

### Database Schema (`agent_goals`)
* `id`: `Uuid`, Primary Key
* `title`: `String(255)`, Not Null
* `description`: `String(4096)`, Nullable
* `status`: `String(50)`, Default "pending"
* `priority`: `Integer`, Default 5 (range [1, 10])
* `progress`: `Float`, Default 0.0 (range [0, 100])
* `identity_id`: `Uuid`, Nullable
* `parent_goal_id`: `Uuid`, Nullable
* `tags`: `JSONB`, Default `[]`
* `metadata`: `JSONB`, Default `{}`
* `due_at`: `DateTime`, Nullable
* `completed_at`: `DateTime`, Nullable
* `created_at`: `DateTime`
* `updated_at`: `DateTime`

### REST API Contracts

#### `GET /api/v1/goals`
* Returns: `200 OK` with list of all goals. Can filter by `status_filter` and `identity_id`.

#### `POST /api/v1/goals`
* Accepts: `title`, `description`, `priority`, `identity_id`, `parent_goal_id`, `tags`, `metadata`, `due_at`.
* Returns: `201 Created` with the new Goal representation.

#### `POST /api/v1/goals/{id}/activate`
* Transition status to `active`. Returns `200 OK`.

#### `POST /api/v1/goals/{id}/complete`
* Transition status to `completed` with 100% progress and set `completed_at`. Returns `200 OK`.

#### `POST /api/v1/goals/{id}/cancel`
* Transition status to `cancelled`. Returns `200 OK`.

#### `POST /api/v1/goals/{id}/progress`
* Accepts: `progress` value in body. Updates progress and handles auto-completion. Returns `200 OK`.

#### `DELETE /api/v1/goals/{id}`
* Deletes goal. Returns `204 No Content`.

---

## 6. Verification Plan

- **Goal Creation Verification**: Verify goal fields are validated correctly and defaults are applied.
- **Goal Completion Invariant**: Set progress to 100.0 and verify that `status` changes to "completed" and `completed_at` is set.
- **Event Bus Integration**: Verify that creating, updating, or completing goals publishes events to `goal.created`, `goal.updated`, and `goal.completed` respectively.
