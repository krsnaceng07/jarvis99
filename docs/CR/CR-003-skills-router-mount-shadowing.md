# CR-003 — Skills Router Mount-Point & Route-Shadowing Fix

**Status:** 🟢 APPROVED + MERGED (2026-07-10, uncommitted)
**Date:** 2026-07-10
**Proposer:** Mavis (orchestrator session `mvs_1eef650acaf648eb92f68ce6275350e9`)
**Approver:** Architect (Rank 0) — pending
**Type:** Frozen-phase correction (route-table misconfiguration, not new feature)
**Frozen phases touched:** Phase 14 (API Gateway), Phase 18 (Dynamic Skill Framework)
**Spec versions affected:** `docs/76_PHASE_14_*` (v1.0 → v1.1)
**Related:** CR-001 §9.6 (discovered during CR-001 validation; "separate, unrelated bug")

---

## 1. Summary

`api/routes/skills.py` declares its routes as `@router.get("/{skill_id}")` etc.
with the documented paths `/api/v1/skills/install`, `/api/v1/skills/{skill_id}`,
etc. (verified: every docstring inside the file says `/api/v1/skills/...`, and
`docs/79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md` §M9 documents them
at the same paths). However, `api/main.py:204` mounts the router with
`prefix="/api/v1"` — **not** `prefix="/api/v1/skills"`. As a result, the
catch-all `GET /{skill_id}` becomes `GET /api/v1/{skill_id}` and shadows
6 single-segment top-level routes.

This is the route-shadowing bug CR-001 §9.6 explicitly tracked as the next CR.

| # | Probe (path) | Symptom | Root cause |
|---|--------------|---------|------------|
| 1 | `missions.list`   → `GET /api/v1/missions`    | 404 `SKILL_I007` | shadowed by `/api/v1/{skill_id}` (id="missions") |
| 2 | `missions.create` → `POST /api/v1/missions`   | 404 `SKILL_I007` | same |
| 3 | `workflows.list`  → `GET /api/v1/workflows`   | 404 `SKILL_I007` | shadowed (id="workflows") |
| 4 | `capabilities.discover` → `GET /api/v1/discover` | 404 `SKILL_I007` | shadowed (id="discover") |
| 5 | `skills.list`     → `GET /api/v1/skills`      | 404 `SKILL_I007` | shadowed (id="skills") |
| 6 | `identity.list`   → `GET /api/v1/identity`    | 404 `SKILL_I007` | shadowed (id="identity") |
| 7 | `goal.list`       → `GET /api/v1/goal`        | 404 `SKILL_I007` | shadowed (id="goal") |

(7 distinct shadowed probes; the matrix counts them as 6 visible failures
because `missions.list` and `missions.create` share a path and are reported
as one row. CR-001's report said "6 failing probes" — both counts are correct
depending on whether you split by path or by row.)

The bug is **entirely a 1-line mount-point error**. The fix is also 1 line.

---

## 2. Reproduction

```text
$ curl -i http://127.0.0.1:8765/api/v1/missions
HTTP/1.1 404 Not Found
content-type: application/json

{
  "success": false,
  "error": {
    "code": "SKILL_I007",
    "message": "Skill 'missions' not found."
  }
}
```

Same response for `/api/v1/workflows`, `/api/v1/discover`, `/api/v1/skills`,
`/api/v1/identity`, `/api/v1/goal` (with the message's `id` swapped).

Multi-segment paths (`/api/v1/scheduler/queue`, `/api/v1/agent/runs`, etc.)
are unaffected because Starlette's matcher prefers static segments over
parameterized ones when comparing **single-segment** paths, and a parameterized
match consumes only one segment.

---

## 3. Root cause

`api/main.py:198-216` registers all routers in this order:

```python
app.include_router(health.router,      prefix="/api/v1")           # 198
app.include_router(memory.router,      prefix="/api/v1")           # 199
app.include_router(auth.router,        prefix="/api/v1")           # 200
app.include_router(users.router,       prefix="/api/v1")           # 201
app.include_router(agent.router,       prefix="/api/v1")           # 202
app.include_router(workflow.router,    prefix="/api/v1")           # 203
app.include_router(skills.router,      prefix="/api/v1")           # 204  ← BUG
app.include_router(capabilities.router, prefix="/api/v1")          # 205
app.include_router(vault.router,       prefix="/api/v1")           # 206
app.include_router(sync.router,        prefix="/api/v1")           # 207
app.include_router(federation.router,  prefix="/api/v1")           # 208
app.include_router(federation_scale.router, prefix="/api/v1")      # 209
app.include_router(admin.router)                                     # 210
app.include_router(observability_router)                            # 211
app.include_router(platform.router)                                  # 212
app.include_router(missions.router)                                  # 213  ← full paths hardcoded
app.include_router(identity.router,   prefix="/api/v1")            # 214
app.include_router(goal.router,       prefix="/api/v1")            # 215
app.include_router(mission_scheduler.router, prefix="/api/v1")      # 216
```

`api/routes/skills.py:265` declares the catch-all:

```python
@router.get("/{skill_id}")
async def get_skill(...) -> Response:
    """GET /api/v1/skills/{skill_id} — Get skill metadata."""
```

With the buggy prefix, the **full path** of this route is
`GET /api/v1/{skill_id}` (root-level catch-all under `/api/v1`), not
`GET /api/v1/skills/{skill_id}` as the docstring and Phase 18 spec
state. Starlette registers the route at that full path; when a request
arrives for `GET /api/v1/missions`, the matcher walks the route table,
finds `/api/v1/{skill_id}` first (because `skills` router is included
before `missions` in the include-order), and dispatches with
`skill_id="missions"`. The handler returns 404 `SKILL_I007`.

`api/routes/missions.py:63` already has hardcoded `/api/v1/missions` paths
and is mounted **without** a prefix at line 213, so its routes are
correctly registered. The conflict is purely between the prefix on
line 204 and the spec's documented path.

---

## 4. Proposed fix

Change **one line** in `api/main.py:204`:

```diff
-    app.include_router(skills.router, prefix="/api/v1")
+    app.include_router(skills.router, prefix="/api/v1/skills")
```

This makes the actual mount match what the docstrings inside
`api/routes/skills.py` already say:

| Internal path | New full path | Spec-documented path |
|---------------|---------------|---------------------|
| `POST /install` | `POST /api/v1/skills/install` | `POST /api/v1/skills/install` ✅ |
| `POST /remove` | `POST /api/v1/skills/remove` | `POST /api/v1/skills/remove` ✅ |
| `GET /` | `GET /api/v1/skills/` | `GET /api/v1/skills/` ✅ |
| `GET /search` | `GET /api/v1/skills/search` | `GET /api/v1/skills/search` ✅ |
| `GET /{skill_id}` | `GET /api/v1/skills/{skill_id}` | `GET /api/v1/skills/{skill_id}` ✅ |

No other code changes. No test changes. No DTO changes. No spec-file
content changes (the spec already says `/api/v1/skills/...`; we're
correcting the implementation to match).

The Phase 14 v1.0 spec section that documents the mount prefix will
be updated to v1.1 to reflect this correction (see §6).

---

## 5. Risk & benefit

- **Risk:** VERY LOW. Pure mount-point correction. The routes being
  shadowed (missions, workflows, discover, skills, identity, goal) are
  already defined by **other** routers that use the correct paths; the
  fix simply un-shadows them. No routes are added, removed, or changed
  in shape. No DTO changes. No contract changes. No test code changes
  (verified: zero test references the old broken paths —
  `tests/test_skill_routes.py` uses `app.include_router(router)` with
  no prefix, so it doesn't care what the production mount is).

- **Benefit:** Makes all 6 currently-404 capability-matrix probes
  return their documented success codes. The capability-matrix gate
  goes from 13 pass / 6 fail / 1 warn → 19 pass / 0 fail / 1 warn
  (the warn is the pre-existing `missions.list` permission-gate
  pending-fix, expected). Restores the Phase 14 API gateway to
  spec-compliance. Eliminates the route-shadowing class of bugs
  from the architecture (no other router in the codebase has a
  bare `/{param}` route at a top-level prefix).

- **Backward compatibility:** **No breaking change** for any
  documented client. The Phase 18 spec and the skills.py docstrings
  have always documented the routes at `/api/v1/skills/...`. Any
  client that is currently calling `/api/v1/install`, `/api/v1/remove`,
  `/api/v1/search`, `/api/v1/{anything}` to talk to the skills API
  is calling an **undocumented** path that was reachable only by
  accident. There is no evidence any such client exists (grep across
  the entire repo and tests returned zero hits). The change makes
  the actual behavior match the documented behavior.

---

## 6. Spec delta to record on approval

Per AGENTS.md §8 step 4:

- `docs/76_PHASE_14_API_GATEWAY_SPECIFICATION.md` — update the section
  that documents router mount points to state that `skills.router`
  is mounted at `prefix="/api/v1/skills"` (was implicitly
  `prefix="/api/v1"` in v1.0). Bump spec to v1.1. Add CR-003 row to
  the Change Control Log.

No other spec change. Phase 18 spec (`docs/79_PHASE_18_*`) is already
correct; no version bump needed for it.

---

## 7. Validation plan (post-approval)

1. Apply the 1-line fix in a feature branch.
2. Add a regression test in `tests/test_skill_routes.py` that
   asserts `app.include_router(router, prefix="/api/v1/skills")`
   produces a route table where `GET /api/v1/missions` and
   `GET /api/v1/discover` are NOT shadowed (i.e. the skills router
   does not contribute a `/{skill_id}` route to the root `/api/v1`
   level). The simplest version: `assert "skills" not in [r.path for
   r in app.routes if "skill" in r.path]` plus `assert all(r.path
   for r in app.routes if "skill" in r.path).startswith("/api/v1/
   skills")`.
3. Run the affected test:
   - `pytest tests/test_skill_routes.py -q` → all pass
   - `pytest tests/test_mission_api.py -q` → all pass (uses
     `/api/v1/missions` which was the worst-affected probe)
   - `pytest tests/test_persistent_execution.py -q` → all pass
     (uses `/api/v1/workflows/{wf_id}`)
4. Run `python scripts/validate_startup.py --in-process` → expect
   `OVERALL: PASS` (19 pass, 0 fail, 1 warn).
5. Run full suite → must remain at or above current 1738 baseline
   minus the 1 documented pre-existing flake (per CR-001 §9.5).
6. Commit with conventional message; the unpushed series becomes:
   ```
   8b8ffb4 fix(kernel,security): CR-001 — register GoalScheduler in DI and seed skill.read scope
   74cfd70 docs(spec,cr): CR-001 — Phase 44 v1.1 + Phase 17 v1.1
   <NEW>   fix(api): CR-003 — mount skills router under /api/v1/skills to fix route shadowing
   <NEW>   docs(spec,cr): CR-003 — Phase 14 v1.1 mount-point correction
   ```
   Each commit is independently revertable; CR-001's commits are not
   amended (architect-approved, frozen).
7. Push to `origin main` only after the in-process gate is green.

---

## 8. STOP & WAIT

Per AGENTS.md §8: **No agent may self-approve a CR. A CR proposal is
itself a STOP-and-wait action.**

This CR is **PROPOSED** until the human architect (Gatekeeper)
explicitly approves. Until then:

- ❌ No code changes to `api/main.py` line 204.
- ❌ No spec changes to `docs/76_PHASE_14_*`.
- ✅ Reading, planning, and authoring this CR are allowed.
- ✅ The 6 capability-matrix probes will continue to return
   404 `SKILL_I007` until CR-003 is approved and merged.

**Authority invoked:** AGENTS.md §1 Rank 2 (Agent Constitution) →
§8 (CR Process) → §6.1 (Specification-First Resolution).

---

## 9. Post-Approval Validation Report

_(populated after approval and merge)_

---

*End of CR-003*
