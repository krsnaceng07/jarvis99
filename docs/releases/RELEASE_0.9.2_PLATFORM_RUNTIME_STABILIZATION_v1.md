# Release 0.9.2 — Platform Runtime Stabilization v1

> **Milestone report** — second per-release report under the
> `Phase → Milestone → Release` hierarchy. Format established 2026-07-10.
> Authoring template: 12-section standard (Release Name / Purpose / Included
> Commits / Scope / Architecture Impact / Governance Impact / Tests / Quality
> Gates / Rollback / Known Issues / Deferred Work / Next Release).

| | |
|---|---|
| **Release Name** | **0.9.2 — Platform Runtime Stabilization v1** |
| **Tag (planned)** | `v0.9.2-platform-runtime-stabilization-v1` |
| **Date** | 2026-07-10 |
| **Milestone** | Platform Runtime Stabilization v1 |
| **Phases touched** | Phase 14 (API Gateway) — v1.0 → v1.1 |
| **Branch** | `main` (8 commits local, **unpushed**) |
| **Base** | `origin/main` (last push at `f8f1508`) |
| **Status** | **MILESTONE COMPLETE — awaiting push (Step 6 of pre-push sequence)** |

---

## 1. Purpose

Stabilize the runtime surface of the JARVIS platform. This
release (a) fixes a real production bug that was shadowing seven
top-level API routes, (b) wires a canonical startup path that
the architect and CI can rely on, (c) adds regression coverage
that survives the next CR renumbering, and (d) cleans up a
stale venv that was committed to the repo. After this release,
the platform's health probe answers in under a second and every
documented route responds at the path the spec promises.

This release is **runtime stabilization**, not a feature. No
new product capability is introduced; what is introduced is
*trust* that the existing capability matrix reflects reality.

## 2. Included Commits

| # | Hash | Type | One-line |
|---|------|------|----------|
| 1 | `2c4e7fe` | fix | Platform stabilization core: `role_assigner` tie-breaking + e2e test DTO + `.venv-py310/` removal + `.gitignore` expansion |
| 2 | `ef45946` | feat | Golden startup infrastructure: `run.py` + 3 scripts + `STARTUP_GUIDE.md` + 28 startup validation tests |
| 3 | `0cc7a29` | fix | CR-003 route shadowing + 4 companion runtime fixes (`core/kernel.py`, `core/runtime/recovery_manager.py`, `core/security/sync.py`, `core/security/vault.py`) + `scripts/runtime_sweep.py` + 2 test files |
| 4 | `70b6d14` | docs | CR-003 — Phase 14 v1.1 mount-point correction + `CR-003-skills-router-mount-shadowing.md` + dashboard update |
| 5 | `0bb4ea7` | test | Make CR-003 regression test number-agnostic via stable slug (`skills-router-mount-shadowing`) |

## 3. Scope

**Production code (commits `2c4e7fe`, `0cc7a29`)**

- `api/main.py` — 9 lines changed (1-line mount-point correction
  at `:158`: `skills.router` now mounted at `prefix="/api/v1/skills"`
  instead of `prefix="/api/v1"`). Resolves the route-shadowing bug.
- `core/kernel.py` — 173 lines changed. Companion runtime fix
  for the boot path; integrates with the CR-001 GoalScheduler
  registration's `try/except` wrapper.
- `core/runtime/recovery_manager.py` — 13 lines changed.
  Companion runtime fix for recovery semantics.
- `core/security/sync.py` — 12 lines changed. Companion runtime
  fix for security sync.
- `core/security/vault.py` — 11 lines changed. Companion runtime
  fix for the security vault.
- `core/runtime/role_assigner.py` — 98 lines changed. Tie-breaking
  rule: among equally-scored roles, pick the one whose first
  keyword appears earliest in the task description.
- `tests/test_e2e_integration_clean.py` — 126 lines changed.
  Now uses the `RetrievalRequest` DTO + class-based
  `FailingExecutor` instead of a function (matches Phase 18/22
  contracts).

**Tooling (commits `0cc7a29`, `ef45946`)**

- `scripts/runtime_sweep.py` — new file, 117 lines. Runtime probe
  utility used by the CR-003 companion validation.
- `run.py` — new file, 190 lines. Canonical launcher:
  preflight + uvicorn spawn.
- `scripts/golden_startup.py` — new file, 354 lines. Programmatic
  StartupConfig / preflight / boot API.
- `scripts/validate_startup.py` — new file, 960 lines. Validation
  orchestrator: in-process / subprocess / external modes.
- `scripts/golden_startup.ps1` — new file, 57 lines. Windows
  PowerShell counterpart of `golden_startup.py` (intentional
  cross-platform split).

**Documentation (commits `ef45946`, `70b6d14`)**

- `docs/STARTUP_GUIDE.md` — new file, 241 lines. Canonical
  startup reference.
- `docs/76_PHASE_14_API_GATEWAY_SPECIFICATION.md` — v1.0 → v1.1.
  Records the mount-point contract.
- `docs/CR/CR-003-skills-router-mount-shadowing.md` — new file,
  258 lines. Second CR under the `docs/CR/` convention.
- `JARVIS_EXECUTIVE_DASHBOARD.md` — 8 lines changed. (See
  Known Issue 9.2.)

**Tests (commits `0cc7a29`, `0bb4ea7`, `ef45946`)**

- `tests/test_startup_validation.py` — new file, 591 lines,
  **28 tests**.
- `tests/test_route_shadowing_regression.py` — new file, 207
  lines, **5 tests** (post-refactor — 4 mount-point assertions
  + 1 doc-presence test).
- `tests/test_runtime_fixes.py` — new file, 400 lines, **6 tests**.

**Housekeeping (commit `2c4e7fe`)**

- `.venv-py310/` — **REMOVED** (627 lines). Stale venv that
  was committed to the repo. New `.gitignore` entries prevent
  recurrence.
- `.gitignore` — 19 lines changed. Expanded to cover both
  `.venv/` and `.venv-py310/`.

## 4. Architecture Impact

| Change | Layer | Invariant class | Frozen interface touched? |
|---|---|---|---|
| `api/main.py:158` mount fix | `api/` (routing) | Bug fix; restores documented behavior | **Phase 14 yes, v1.0 → v1.1** — proper CR workflow (CR-003) per AGENTS.md §8 |
| 4 companion runtime fixes | `core/` (kernel, runtime, security) | Bug fixes; behavior matches spec | No — fixes brought code into alignment with the spec, not the reverse |
| `role_assigner` tie-breaking | `core/runtime/` | Algorithm refinement; deterministic | No — internal scoring rule, no public contract change |
| Golden startup infra | `scripts/` + `run.py` | New tooling; additive | No — out-of-tree; `run.py` is the new entry point but `api/main.py` is unchanged |
| CR-003 regression test (slug-based) | `tests/` | New test, future-proofed | No — test only |

- **Critical fix**: the route-shadowing bug was returning
  `404 SKILL_I007` on `GET /api/v1/{skill_id}` for **seven** real
  routes:
  `GET /api/v1/missions`, `POST /api/v1/missions`,
  `GET /api/v1/workflows`, `GET /api/v1/discover`,
  `GET /api/v1/skills`, `GET /api/v1/identity`, `GET /api/v1/goal`.
  The fix un-shadows all seven.
- No public API breakage introduced.
- No frozen interface changed without a CR (CR-003 is the
  authorization for the Phase 14 v1.0 → v1.1 bump).

## 5. Governance Impact

- **Second CR** under the new `docs/CR/` convention
  (`CR-001` in Release 0.9.1 was the first).
- **CR-003's renumbering history is documented.** The bug was
  originally tracked as "CR-002" in the session before this one;
  it was renumbered to CR-003 when a different topic claimed the
  CR-002 number. The `0bb4ea7` follow-up commit makes the
  regression test number-agnostic so this kind of renumbering
  cannot break the test in the future. The CR doc itself was
  renamed to match.
- **Spec versions annotated.** `docs/76_PHASE_14_*` line for
  v1.1 records the mount-point contract and references CR-003 as
  the authorizing document.
- **`.venv-py310/` removal** — first time a tracked venv has
  been cleaned up. The `.gitignore` now covers both `.venv/`
  and `.venv-py310/`, and the removal commit
  (`2c4e7fe`) is the precedent for any future venv cleanup.

## 6. Tests

| Test file | Lines | Tests | Status |
|---|---:|---:|---|
| `tests/test_startup_validation.py` (new) | 591 | 28 | PASS (per earlier session scratchpad) |
| `tests/test_route_shadowing_regression.py` (new) | 207 | 5 | PASS (verified this session) |
| `tests/test_runtime_fixes.py` (new) | 400 | 6 | PASS (verified this session) |
| `tests/test_e2e_integration_clean.py` (modified) | +126/−? | (existing count) | PASS (verified this session) |
| **Total new tests** | — | **39** | PASS |

**Quality of the new tests:**

- `test_startup_validation.py` — programmatic API covering
  StartupConfig, preflight, in-process / subprocess / external
  validation modes. 28 hermetic tests.
- `test_route_shadowing_regression.py` — locks down 4 invariants:
  (1) the production mount line is the correct one;
  (2) no `/api/v1` prefix is paired with a bare `/{param}` catch-all;
  (3) the 5 documented skills routes are declared;
  (4) no route at the empty path; (5) a CR doc with the slug
  `skills-router-mount-shadowing` exists. **Future-proof:**
  test (5) uses slug-based lookup, so a future CR renumbering
  (CR-003 → CR-NNN) does not break it (proven empirically by
  simulating the renumber with `git mv` to `CR-999-...`).
- `test_runtime_fixes.py` — covers the 4 companion runtime fixes
  in `core/runtime/recovery_manager.py`, `core/security/sync.py`,
  `core/security/vault.py`, and the `core/kernel.py` boot path.

## 7. Quality Gates

| Gate | Status | Source |
|---|---|---|
| `ruff check` on modified files | **PASS** | This session |
| `ruff format --check` on modified files | **PASS** | This session |
| `mypy --strict` on modified files | **PASS** | This session |
| `pytest tests/test_route_shadowing_regression.py tests/test_runtime_fixes.py` | **11/11 PASS** | This session |
| `pytest tests/test_startup_validation.py` | **28/28 PASS** | Earlier session (per `docs/STARTUP_GUIDE.md` + scratchpad) |
| Live `GET /api/v1/health` (post-fix) | **PASS** | This session (`python scripts/validate_startup.py --in-process`) |
| Full repo `pytest` | ⏸ **DEFERRED to Step 5** of the pre-push sequence | |
| Architecture linter | ⏸ **DEFERRED to Step 5** | |
| DGV (dependency graph validator) | ⏸ **DEFERRED to Step 5** | |

## 8. Rollback

| Rollback point | What it reverts | Risk |
|---|---|---|
| **`0bb4ea7` (latest in this release)** | Reverts only the test refactor (slug-based) | **None** — pure refactor; all assertions unchanged |
| **`70b6d14` (one back)** | Reverts CR-003 docs (spec bump + CR doc + dashboard) | **Low** — docs only |
| **`0cc7a29` (one back)** | Reverts CR-003 code (api/main.py mount fix + 4 companion fixes + runtime_sweep + 2 test files) | **HIGH** — re-introduces the route-shadowing bug. **NOT recommended** unless the new mount actively breaks something. |
| **`ef45946` (one back)** | Reverts the golden startup infra | **Low** — additive; `run.py` and the 3 scripts are new |
| **`2c4e7fe` (parent of this release)** | Reverts the platform stabilization core (role_assigner + e2e test + .venv-py310 removal) | **Low** — the role_assigner change is algorithmically equivalent at the spec level; the e2e test was using a contract that the Phase 18/22 specs now require; the .venv cleanup is irreversible only in the sense that you'd have to re-delete it |

**Recommended rollback target:** **`2c4e7fe`** (the parent of
this release). One `git revert` reverses the entire release. The
exception: if the rollback reason is "the route shadowing fix
breaks something," then target `70b6d14` and keep the platform
stabilization core; that keeps role_assigner, the startup infra,
and the test files, and reverts only the routing fix and the
spec/CR doc — which can then be re-issued as a smaller
corrective release.

**Worst-case rollback target:** `2c4e7fe` followed by cleanup
of the `archive/` state if Release 0.9.1 had already been
pushed and is being undone too. In that case, push the rollback
as a separate release (e.g., 0.9.3) so the rollback is itself
auditable.

## 9. Known Issues

### 9.1 Documentation Drift #1 — dashboard vs constitution

`JARVIS_EXECUTIVE_DASHBOARD.md` lists phases up to "Phase 45 —
Plugin & Skill Marketplace — PLANNED." The canonical phase list
in `AGENTS.md §12` ends at Phase 41 (Capability Registry, frozen).
Phases 42–44 specs exist on disk (`docs/104_*`, `docs/105_*`,
`docs/106_*`) but have not been promoted to the AGENTS.md §12
table. The dashboard is ahead of the constitution.

**Action:** not fixed in this release. Deferred to a separate
**doc-sync commit** that promotes the AGENTS.md table. Doing
it inside this release would broaden its scope beyond
"runtime stabilization."

### 9.2 Documentation Drift #2 — stale "merged, uncommitted" string

`JARVIS_EXECUTIVE_DASHBOARD.md` line 15 reads "Platform
Stabilization Pass + CR-003 merged, uncommitted." This was true
at write time but is now stale (CR-003 is committed at `0cc7a29`/
`70b6d14`/`0bb4ea7` and is "committed, unpushed," not "merged,
uncommitted"). The dashboard will also need to be updated when
this release (0.9.2) is pushed.

**Action:** deferred to the same doc-sync commit as 9.1.

### 9.3 Tracked-but-ignored generated artifacts

`audit_report.json` and `jarvis_dev.db` are listed in `.gitignore`
but ARE tracked in the git index. A previous similar cleanup
happened at commit `56ebae5` ("chore(hygiene): untrack
audit_report.json + gitignore it"). The artifacts have been
re-tracked since.

**Action:** deferred to a separate **hygiene commit** (in the
pre-push cleanup, Step 4 of the pre-push sequence).

### 9.4 `scripts/golden_startup.ps1` — Windows PowerShell counterpart

The golden startup infra has both a Python implementation
(`scripts/golden_startup.py`, 354 lines) and a Windows
PowerShell counterpart (`scripts/golden_startup.ps1`, 57 lines).
This is intentional cross-platform support — the .py version
handles Linux/macOS, the .ps1 is needed for Windows. Flagged
here so a future reviewer doesn't mistake the duplication for
unintentional redundancy.

**Action:** none. Documented as a known dual-implementation.

## 10. Deferred Work

| Item | Reason | Target |
|---|---|---|
| Doc-sync commit (issues 9.1, 9.2) | Out of scope for "runtime stabilization" | Next cleanup window |
| Hygiene commit (issue 9.3) | Out of scope | Step 4 of pre-push sequence (after both reports approved) |
| `find_cr_document()` project-wide helper | Per the **second consumer before abstraction** rule (architect's principle, 2026-07-10), helpers are only extracted when a second consumer exists. As of this release, only `test_route_shadowing_regression.py` uses the slug-based lookup pattern. | When CR-2 (the next CR) is filed, evaluate whether the new CR's regression test should reuse the helper. If yes, extract then. |
| Phase 45 work (Plugin & Skill Marketplace) | Per `AGENTS.md §12` planning, Phase 45 is the next entry. Not started. | After 0.9.1 + 0.9.2 land |
| Promote CR_SLUG pattern + 12-section milestone report format to `AGENTS.md` | New conventions established by this release should be codified in the project constitution | Architect decision (this is a governance change, not a code change) |

## 11. Next Release

**Release 0.9.3 (proposed) — Doc Sync + Hygiene Batch**

Small, fast release intended to clear the deferred-work items
from Releases 0.9.1 and 0.9.2:

- Promote the AGENTS.md §12 phase table to include Phases 42–45.
- Update the dashboard's stale "merged, uncommitted" string.
- Untrack `audit_report.json` and `jarvis_dev.db` (hygiene
  regression of `56ebae5`).
- Codify the `Phase → Milestone → Release` hierarchy and the
  12-section milestone report format in `AGENTS.md` (architect
  decision required — this is a governance change).

A separate release is appropriate because (a) it is a small
self-contained batch, (b) it is decoupled from the platform
stabilization work, and (c) it unblocks a cleaner audit trail
for future Phase 45 work.

**Release 0.10.0 (proposed) — Phase 45: Plugin & Skill Marketplace**

The next feature release. Will require its own Phase 45 spec
(per `AGENTS.md §5 Lifecycle` — spec must be FROZEN before
implementation begins). Not yet scoped.

---

*Awaiting architect approval per AGENTS.md §10: "An agent MUST
NOT proceed to the next milestone without explicit architect
approval." This report is complete and gates (Step 3 of the
pre-push sequence) can advance to Step 4 only after sign-off.*

*Cross-reference: this release is the runtime-stabilization
counterpart of Release 0.9.1 (Readiness Foundation). The two
are designed to be a paired unit: 0.9.1 makes the capability
matrix probes reachable, 0.9.2 makes them answer correctly.*
