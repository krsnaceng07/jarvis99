# Release 0.9.1 — Readiness Foundation

> **Milestone report** — first per-release report under the
> `Phase → Milestone → Release` hierarchy. Format established 2026-07-10.
> Authoring template: 12-section standard (Release Name / Purpose / Included
> Commits / Scope / Architecture Impact / Governance Impact / Tests / Quality
> Gates / Rollback / Known Issues / Deferred Work / Next Release).

| | |
|---|---|
| **Release Name** | **0.9.1 — Readiness Foundation** |
| **Tag (planned)** | `v0.9.1-readiness-foundation` |
| **Date** | 2026-07-10 |
| **Milestone** | Readiness Foundation |
| **Phases touched** | Phase 17 (Authentication & Authorization) — v1.0 → v1.1 · Phase 44 (Mission Scheduler) — v1.0 → v1.1 |
| **Branch** | `main` (8 commits local, **unpushed**) |
| **Base** | `origin/main` (last push at `f8f1508` per `git log @{u}`; pre-push diverges 8 commits) |
| **Status** | **MILESTONE COMPLETE — awaiting push (Step 6 of pre-push sequence)** |

---

## 1. Purpose

Prepare the JARVIS runtime for the next phase of work by eliminating
two latent production-blocking defects that the capability-matrix
probe uncovered, and by retiring a pile of stale governance artifacts
that no longer reflect the canonical constitution. After this release,
every blocked-by-bug probe in the capability matrix that can be
attributed to this milestone is green, and the governance surface
matches the actual project rules.

This release is the **foundation**, not the feature work. The new
feature work (Phase 45) sits on top of this release and would have
failed every probe had it shipped first.

## 2. Included Commits

| # | Hash | Type | One-line |
|---|------|------|----------|
| 1 | `8b8ffb4` | fix | CR-001 — register `GoalScheduler` in DI and seed `skill.read` scope |
| 2 | `74cfd70` | docs | CR-001 — Phase 44 v1.1 (DI registration) and Phase 17 v1.1 (skill.read scope) |
| 3 | `af3be0e` | chore | Archive legacy governance + consolidate ADR registry |

## 3. Scope

**Production code (commit `8b8ffb4`)**

- `core/kernel.py` — 9 lines added. Wraps `GoalScheduler` DI registration
  in `try/except` + `logger.warning(...)` so a Phase 44 init failure
  no longer blocks kernel boot. Singleton registered as
  `GoalScheduler` in the kernel DI container, taking `event_bus` as
  its only constructor dependency.
- `core/security/seed_service.py` — 1 line added. Adds `skill.read` to
  the default scope seed so the admin role inherits it (admin inherits
  every seeded scope; existing installations pick up the new scope
  automatically on next boot, since admin re-syncs on boot).

**Tooling (commit `8b8ffb4`)**

- `scripts/capability_matrix.py` — new file, 730 lines, 24,583 bytes.
  Real source code (NOT generated). It *generates* the
  `JARVIS_CAPABILITY_MATRIX.{md,json}` outputs which ARE in
  `.gitignore`. 20-probe matrix; 2 of those probes had wrong paths
  in an earlier draft (`scheduler.list` and `capabilities.discover`)
  and now probe the correct routes.

**Documentation (commit `74cfd70`)**

- `docs/78_PHASE_17_AUTHENTICATION_AUTHORIZATION_SPECIFICATION.md` —
  v1.0 → v1.1. Adds the `skill.read` default scope to the spec
  body and the seeded scopes table.
- `docs/106_PHASE_44_MISSION_SCHEDULER_SPECIFICATION.md` — v1.0 →
  v1.1. Records the DI registration contract and the
  init-failure-tolerance contract.
- `docs/CR/CR-001-mission-scheduler-and-skill-read.md` — new file,
  425 lines. First CR to live under the new `docs/CR/` convention.

**Governance archive (commit `af3be0e`)**

- `archive/legacy_governance/.antigravity/` — 9 files, 25,683 bytes
  total. Real content, not empty (moved from project root, not
  deleted).
- `archive/legacy_methodology/` — 2 files, 13,768 bytes.
- `archive/legacy_adapters/` — 1 file, 2,055 bytes.
- `archive/legacy_tools/.claude/skills/` — 3 files.
- `docs/06_ARCHITECTURE_DECISION_RECORDS.md` — 130 lines changed.
  Consolidated the ADR registry: 16 ADRs (ADR-001 through
  ADR-016), split into foundational stack (ADR-012..016) and
  architecture-pattern (ADR-001..011) groups.
- `docs/60_MASTER_INDEX.md` — 3 lines changed. Updated ADR pointer.
- `docs/adr/README.md` — 16 lines removed. Old ADR index, replaced
  by `docs/06_*`.
- `.gitignore` — 20 lines changed. Added patterns to ignore
  regenerated governance artifacts.

## 4. Architecture Impact

| Change | Layer | Invariant class | Frozen interface touched? |
|---|---|---|---|
| `GoalScheduler` DI singleton | `core/` (kernel) | New dependency wiring | **No** — Phase 44 v1.1 spec-bump authorizes it |
| `skill.read` default scope | `core/security/` | New permission gate | **Phase 17 yes, v1.0 → v1.1** — proper CR/ADR workflow per AGENTS.md §8 |
| 20-probe capability matrix tool | `scripts/` | Test harness | **No** — out-of-tree |
| ADR consolidation | `docs/` | Documentation | **No** — docs only |

- No public API breakage.
- No frozen interface changed without a CR (CR-001 is the
  authorization for both Phase 17 and Phase 44 deltas).
- DI graph gains 1 new singleton; existing call sites are
  unchanged.

## 5. Governance Impact

- **First use of the new `docs/CR/` convention** for Change
  Requests. The directory and the CR-doc template were established
  earlier in the project; CR-001 is the first CR written against
  the template.
- **Legacy governance documents moved to `archive/legacy_*/`**
  rather than deleted. The `archive/` directory has a `README.md`
  (113 lines) explaining the policy: nothing in `archive/` is
  authoritative; it is preserved provenance, not a normative
  source.
- **ADR registry consolidated.** The pre-existing
  `docs/adr/ADR-001-event-bus.md` was a single-file stub; the
  consolidated registry at `docs/06_ARCHITECTURE_DECISION_RECORDS.md`
  is the single canonical index. `docs/adr/README.md` is removed.
- **No spec was re-rewritten to match code** (per
  `AGENTS.md §6.1 Specification-First Resolution Rule`). CR-001
  spec deltas were filed BEFORE the code landed.

## 6. Tests

| Source | Status |
|---|---|
| `scripts/capability_matrix.py` 20-probe matrix | 6 newly pass with CR-001 fix; 6 still fail (route-shadowing, tracked in CR-003 — Release 0.9.2); 8 unaffected |
| `pytest tests/test_runtime.py` | Pre-existing pass; no change |
| `pytest tests/test_api_gateway.py` | Pre-existing pass; no change |
| `pytest tests/test_federation.py` | Pre-existing pass; no change |
| Pre-existing test flake (CR-001 §9.5) | **NOT a regression** — confirmed by validation report |

**New test files: 0.** This release's correctness is asserted
through the capability matrix (live probes) and through the CR-001
post-approval validation report (CR-001 §9). The absence of a new
test file is appropriate for a small surgical DI + scope fix; if
this release grew any larger, a dedicated test file would be
required by `AGENTS.md §9` (general coverage ≥ 80%).

## 7. Quality Gates

| Gate | Status | Source |
|---|---|---|
| `ruff check` on modified files | **PASS** | CR-001 §9.1 |
| `ruff format --check` on modified files | **PASS** | CR-001 §9.1 |
| `mypy --strict` on modified files | **PASS** | CR-001 §9.1 |
| Live `/api/v1/scheduler/queue` returns 200 | **PASS** | CR-001 commit message + §9.4 |
| Admin JWT contains `skill.read` | **PASS** | CR-001 commit message + §9.4 |
| Full repo `pytest` | ⏸ **DEFERRED to Step 5** of the pre-push sequence | (this release only modified 3 source files; no reason to assume a wider regression, but the gate must run) |
| Architecture linter | ⏸ **DEFERRED to Step 5** | |
| DGV (dependency graph validator) | ⏸ **DEFERRED to Step 5** | |

## 8. Rollback

| Rollback point | What it reverts | Risk |
|---|---|---|
| **`8b8ffb4` (latest in this release)** | Reverts only the production code (DI + scope) | Low — pure additive; no other code calls GoalScheduler yet |
| **`74cfd70` (mid-release)** | Reverts production code AND spec bumps | Low — specs return to v1.0, no callers depend on v1.1 yet |
| **`af3be0e` (parent of this release)** | Adds archive moves + ADR consolidation | **Medium** — the archive move is destructive from `git`'s POV (it's a rename), so `git restore` from `archive/` is the only path. Real content is preserved. |

**Recommended rollback target:** `af3be0e` (parent). One
`git revert` reverses the entire release with the lowest cognitive
load; re-applying is also a single `git revert` of the revert.

**Security note:** if this release has been live and admin tokens
have been issued with `skill.read` in the permissions claim, those
tokens continue to have `skill.read` even after rollback. The
scope is security-neutral — it expands the admin's effective
permissions to include a read-only view it should already have
had. The rollback target does not need to invalidate issued
tokens.

## 9. Known Issues

### 9.1 Documentation Drift #1 — dashboard vs constitution

`JARVIS_EXECUTIVE_DASHBOARD.md` lists phases up to "Phase 45 —
Plugin & Skill Marketplace — PLANNED." The canonical phase list
in `AGENTS.md §12` ends at Phase 41 (Capability Registry, frozen).
Phases 42–44 specs exist on disk (`docs/104_*`, `docs/105_*`,
`docs/106_*`) but have not been promoted to the AGENTS.md §12
table. The dashboard is ahead of the constitution.

**Action:** not fixed in this release. Deferred to a separate
**doc-sync commit** that promotes the AGENTS.md table. Doing it
inside this release would broaden its scope beyond "readiness
foundation."

### 9.2 Documentation Drift #2 — stale "merged, uncommitted" string

`JARVIS_EXECUTIVE_DASHBOARD.md` line 15 reads "Platform
Stabilization Pass + CR-003 merged, uncommitted." This was true
at write time but is now stale (CR-003 is committed at `0cc7a29`/
`70b6d14`/`0bb4ea7` and is "committed, unpushed," not "merged,
uncommitted"). The dashboard will also need to be updated when
this release (0.9.1) is pushed.

**Action:** deferred to the same doc-sync commit as 9.1.

### 9.3 Tracked-but-ignored generated artifacts

`audit_report.json` and `jarvis_dev.db` are listed in `.gitignore`
but ARE tracked in the git index. A previous similar cleanup
happened at commit `56ebae5` ("chore(hygiene): untrack
audit_report.json + gitignore it"). The artifacts have been
re-tracked since.

**Action:** deferred to a separate **hygiene commit**:
```
git rm --cached audit_report.json jarvis_dev.db
git commit -m "chore(hygiene): untrack audit/db artifacts (regression of 56ebae5)"
```
Doing this in the pre-push cleanup (Step 4 of the pre-push
sequence, AFTER this report is approved) keeps the cleanup
visible in history as a separate, attributable commit.

## 10. Deferred Work

| Item | Reason | Target |
|---|---|---|
| Doc-sync commit (issues 9.1, 9.2) | Out of scope for "readiness foundation" — touches dashboard, not readiness | Next available cleanup window |
| Hygiene commit (issue 9.3) | Out of scope for "readiness foundation" — touches .gitignore behavior, not readiness | Step 4 of pre-push sequence (after this report is approved) |
| Route-shadowing fix | Belongs to its own release (Platform Runtime Stabilization v1) | **Release 0.9.2** |
| Phase 45 work | Not started | After 0.9.1 + 0.9.2 land |

## 11. Next Release

**Release 0.9.2 — Platform Runtime Stabilization v1**

The companion release to this one. Lands the route-shadowing
fix (CR-003), the golden startup infrastructure, the platform
stabilization core, and the future-proof CR-003 regression test.
Together, 0.9.1 and 0.9.2 form a paired unit: 0.9.1 makes
probes reachable, 0.9.2 makes them answer correctly.

A separate milestone report (`docs/releases/RELEASE_0.9.2_PLATFORM_RUNTIME_STABILIZATION_v1.md`)
will be drafted in the next session step and will require its own
architect approval before pushing.

---

*Awaiting architect approval per AGENTS.md §10: "An agent MUST
NOT proceed to the next milestone without explicit architect
approval." This report is complete and gates (Step 3 of the
pre-push sequence) can advance to Step 4 only after sign-off.*
