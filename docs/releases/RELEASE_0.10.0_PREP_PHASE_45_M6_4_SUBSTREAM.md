# Release 0.10.0-prep — Phase 45 M6.4 Sub-Stream (Distributed Execution)

> **Milestone report** — fourth per-release report under the
> `Phase → Milestone → Release` hierarchy (12-section format).
> First prep-tagged release: lands the M6.4 sub-stream on `main` but
> holds the v0.10.0 FINAL tag until the rest of Phase 45 (M6.1.B, M6.2.A/B,
> M6.3.A/B, M6.5.A/B) freezes individually per `docs/108_PHASE_45_IMPLEMENTATION_PLAN.md` §3
> and the plan §8 STOP condition.

| | |
|---|---|
| **Release Name** | **0.10.0-prep — Phase 45 M6.4 Sub-Stream (Distributed Execution)** |
| **Tag (planned, deferred)** | `v0.10.0-persistent-autonomous-runtime` (held until FINAL gate; M6.4 sub-stream tagged separately as `v0.10.0-prep-distributed-execution` if architect calls) |
| **Date** | 2026-07-11 |
| **Milestone** | Phase 45 / M6.4 (Distributed Execution — Transport, Router, WorkerRegistry, LeaderElection) |
| **Phases touched** | Phase 45 (v1.2 FROZEN-amended) — additive only, no spec change |
| **Branch** | `phase45/transport` (7 commits) → `main` (merge commit, `--no-ff` per `docs/44_GIT_WORKFLOW.md`) |
| **Base** | `main` at `ce8ebdb` (0.9.4 SHIPPED) + `31e6897` (0.9.5-prep housekeeping); merge base = `ce8ebdb` |
| **Status** | **MILESTONE COMPLETE on `phase45/transport` — awaiting merge to `main`** |

---

## 1. Purpose

Phase 45 (Persistent Autonomous Runtime, Goal #6) is the next major
release after 0.9.4. Its full scope (per `docs/108_PHASE_45_IMPLEMENTATION_PLAN.md`)
is partitioned into **five sub-goals** (M6.1 actor foundation, M6.2 scheduler,
M6.3 crash recovery, M6.4 distributed execution, M6.5 observability)
plus a FINAL freeze gate.

**This release lands the M6.4 sub-stream** (Distributed Execution) on
`main` while keeping the other four sub-goals on separate branches.
The M6.4 sub-stream is the largest, most architecturally novel of the
five: it introduces the **transport layer** (local + remote over Redis
pub/sub) that all later sub-milestones (M6.3 recovery, M6.5 observability,
M6.1 rehydration across processes) will consume. Landing it first
unblocks parallel work on the other sub-milestones against a stable
transport contract.

**Why "prep" and not the v0.10.0 FINAL tag:** the FINAL gate per plan
§3 + §8 is held until ALL Phase 45 sub-milestones (M6.1.B, M6.2.A/B,
M6.3.A/B, M6.5.A/B) pass individually. The M6.4 sub-stream is the
first of five to land; once the others follow, a single v0.10.0 FINAL
release doc + tag will close the milestone. Until then, the M6.4
sub-stream is **v0.10.0-prep** — a `main` snapshot that is mergeable
+ consumable, but not yet a tagged release.

## 2. Included Commits

| # | Hash | Type | One-line |
|---|------|------|----------|
| 1 | `1401b81` | feat(phase45) | M6.4 transport layer + worker registry + distributed router (lifted from `wt/5a39ff05` `2405abf`) |
| 2 | `eb54911` | docs(phase45) | lift M6.4.A milestone report from `wt/5a39ff05` (governance protocol close) |
| 3 | `337ca64` | feat(phase45) | M6.4.B.2 RemoteTransport over Redis pub/sub + SETNX leases |
| 4 | `7e53c69` | docs(phase45) | retrofit M6.4 governance from `wt/5a39ff05` — spec v1.2 / plan v1.1 / CR-4 / state machine |
| 5 | `0e1b593` | feat(phase45) | M6.4.B code-completion — DistributedRouter REMOTE_PREFERRED + WorkerRegistry task tracking + envelope bug fix |
| 6 | `fff4daa` | feat(phase45) | M6.4.C — LeaderElection state machine (STRETCH) |
| 7 | `7abfe19` | chore(state) | close post-M6.4.C bookkeeping — refresh .ai/ on `phase45/transport` |
| 8 | (this) | docs(phase45) | M6.4 sub-stream pre-merge refresh — AGENTS.md §12 row 45 STAGED + dashboard refresh + this release doc |

The M6.4.A delegated-approval was recorded in the report lift commit
(`eb54911`); the 0.9.5-prep housekeeping on `main` (`31e6897`) is
**not** part of this release — it is already documented as a separate
housekeeping entry on `main`.

## 3. Scope

**Production code (commits `1401b81`, `337ca64`, `0e1b593`, `fff4daa`)**

- `core/mission/mission_transport.py` — NEW. The `MissionTransport`
  Protocol (A-1 architecture invariant). One method, one return
  type — distributed routing and leader election both speak only
  to this Protocol.
- `core/mission/transports/__init__.py` — NEW. Re-exports the
  Protocol + concrete transports.
- `core/mission/transports/local.py` — NEW. In-process transport
  used as the local-mode default and as the test stub.
- `core/mission/transports/envelope.py` — NEW. `TransportEnvelope`
  Protocol + `EnvelopeV1` codec (D-5 wire-format layer; msgpack+zstd;
  forward-compat `extra='ignore'`). Bug-fixed at `0e1b593` to handle
  pydantic 2.13.4 `bytes` field serialization correctly.
- `core/mission/transports/redis.py` — NEW. `RemoteTransport` over
  Redis pub/sub with SETNX leases. Cross-client delivery, prefix
  customization, Lua-script atomicity, lifecycle lockdown.
- `core/mission/worker_registry.py` — NEW. `WorkerRegistry` with
  15s grace, idempotent register/heartbeat, list_active sweep+read
  single-txn. Extended at `0e1b593` with `mark_task_started` /
  `mark_task_completed` (idempotent on `(worker_id, wave_run_id)`)
  for D-4 exactly-once.
- `core/mission/distributed_router.py` — NEW. `DistributedRouter`
  (A-1 invariant; speaks only to `MissionTransport` Protocol;
  D-2 append-only routing log; D-3 unique-index dedup). Extended at
  `0e1b593` with `_route_remote` + `REASON_ROUTED_REMOTE` for
  REMOTE_PREFERRED behavior.
- `core/mission/worker_process.py` — NEW. CLI worker process.
  No secret-on-cmdline (per spec §8.3); default heartbeat 10s.
- `core/mission/leader_election.py` — NEW (M6.4.C). `LeaderElection`
  single-shot state machine + `LeaderRole` enum (CANDIDATE / FOLLOWER
  / LEADER / STEPPED_DOWN / RELEASED / CLOSED) + `LeaderElectionError`.
  Speaks only to `MissionTransport` Protocol per A-1.
- `api/routes/distributed_pool.py` — NEW. REST endpoints under
  `/api/v1/distributed/*` (auth `platform.admin`).
- `core/runtime/mission_models.py` — additive columns only
  (`WorkerRegistryModel` + `TaskRoutingLogModel` + D-3 unique index).
  Per Phase 34 contract (FROZEN), no renames.

**Tests (commits `1401b81`, `337ca64`, `0e1b593`, `fff4daa`)**

- `tests/test_distributed_router.py` — 47 tests (M6.4.A router scaffold)
- `tests/test_worker_registry.py` — 32 tests (M6.4.A worker registry + grace)
- `tests/test_worker_process.py` — 8 tests (M6.4.A worker CLI)
- `tests/test_local_transport.py` — 19 tests (M6.4.A local transport)
- `tests/test_distributed_pool_route.py` — 23 tests (M6.4.A REST endpoints)
- `tests/test_transport_envelope.py` — 39 tests (M6.4.B.1 codec)
- `tests/test_remote_transport_exhaustive.py` — 56 tests (M6.4.B.2 Redis)
- `tests/test_distributed_router_remote_preferred.py` — 23 tests
  (M6.4.B code-completion: REMOTE_PREFERRED + task accounting + A-1 AST
  inspection)
- `tests/test_leader_election.py` — 33 tests across 14 classes
  (M6.4.C: state machine + split-brain simulations + cross-client path)

**Documentation (commits `eb54911`, `7e53c69`, `7abfe19`, this commit)**

- `docs/reports/PHASE45_M6_4_A_REPORT.md` — M6.4.A milestone report
  (lifted from `wt/5a39ff05` so the freeze protocol can recognize the
  gate as documented).
- `docs/reports/PHASE45_M6_4_B_REPORT.md` — M6.4.B milestone report
  (B.1 + B.2 + code-completion; 247 net new tests).
- `docs/reports/PHASE45_M6_4_C_REPORT.md` — M6.4.C milestone report
  (LeaderElection; 33 tests; 412% of plan §3 floor of ≥ 8).
- `docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md` —
  v1.2 (governance retrofit; CR-1/2/3/4 applied).
- `docs/108_PHASE_45_IMPLEMENTATION_PLAN.md` — v1.1 (governance retrofit;
  matches the on-disk implementation per AGENTS.md §6.1 resolution).
- `docs/cr/CR-1_phase45_state_typo_alignment.md` — DRAFT (M6.1.A gate).
- `docs/cr/CR-2_phase45_recovery_event_taxonomy.md` — DRAFT (M6.3.A gate).
- `docs/cr/CR-3_phase45_phase26_additive_column.md` — DRAFT (M6.3.A gate).
- `docs/cr/CR-4_phase45_d4_idempotency_d5_envelope.md` — APPROVED
  (2026-07-09; retrofitted to `phase45/transport` at `7e53c69`).
- `docs/mission_state_machine.md` — 8-event taxonomy (frozen reference).
- `docs/releases/RELEASE_0.10.0_PREP_PHASE_45_M6_4_SUBSTREAM.md` — this file.
- `AGENTS.md` §12 row 45 — STAGED for v0.10.0.
- `JARVIS_EXECUTIVE_DASHBOARD.md` — Phase 45 status updated to STAGED;
  risks R-D, R-E closed; test velocity to 2041; Layer 5 to ~99%.
- `.ai/FREEZE_LEDGER.md` — Updated footer bumped to merge date.

## 4. Architecture Impact

| Change | Layer | Invariant class | Frozen interface touched? |
|---|---|---|---|
| `MissionTransport` Protocol | `core/mission/` | NEW abstract type (A-1 architecture invariant) | No — new, not modification |
| `LocalTransport` / `RemoteTransport` | `core/mission/transports/` | NEW concrete implementations | No — new |
| `TransportEnvelope` + `EnvelopeV1` | `core/mission/transports/` | NEW wire-format layer (D-5) | No — new |
| `WorkerRegistry` | `core/mission/` | NEW state holder (D-1 15s grace) | No — new |
| `DistributedRouter` | `core/mission/` | NEW coordinator (D-2, D-3) | No — new |
| `WorkerProcess` CLI | `core/mission/` | NEW process | No — new |
| `LeaderElection` | `core/mission/` | NEW state machine (M6.4.C STRETCH) | No — new |
| `/api/v1/distributed/*` REST routes | `api/routes/distributed_pool.py` | NEW routes (auth `platform.admin`) | No — new |
| Additive mission_models columns | `core/runtime/mission_models.py` | ADDITIVE per Phase 34 FROZEN contract | **No** — additive only, no rename |
| Spec v1.2 amendment (CR-4) | `docs/107_*.md` | v1.1 → v1.2 (CR-4 applied) | **Yes** — but via approved CR per AGENTS.md §8 |

- **No public API breakage introduced.** All additions are net-new
  modules + additive DB columns. Existing routes, DTOs, and contracts
  are unchanged.
- **Frozen interfaces respected.** Phase 34 (`core/runtime/mission_models.py`)
  is touched only additively per its FROZEN contract. The Phase 45
  spec amendment (v1.1 → v1.2) was processed via CR-4 with explicit
  human architect approval (2026-07-09), retrofitted to the branch
  at `7e53c69` so the on-disk code is now authorized (per AGENTS.md
  §6.1 Specification-First Resolution Rule).
- **A-1 invariant honored:** `DistributedRouter` and `LeaderElection`
  speak only to the `MissionTransport` Protocol + `WorkerRegistry`.
  AST-verified by
  `tests/test_distributed_router_remote_preferred.py::TestA1NoConcreteTransportImport`
  and by static inspection of `core/mission/leader_election.py`
  (only `MissionTransport` is imported).
- **No new third-party dependencies.** `fakeredis>=2.20.0` and
  `redis>=5.0.4` are already pinned in `pyproject.toml`; `msgpack`
  and `zstd` are already available in the test environment.

## 5. Governance Impact

- **No new CR beyond CR-4.** CR-4 (D-4 + D-5) is the only Phase 45
  governance change in this release. It was approved by the architect
  on 2026-07-09 and retrofitted to the branch at `7e53c69`.
- **Spec v1.1 → v1.2 amendment** under CR-4 (D-4 + D-5). The
  amendment is closed and frozen; no further changes planned.
- **Plan v1.0 → v1.1 amendment** matches the on-disk implementation
  per AGENTS.md §6.1. The implementation did not retro-fit the
  spec — the spec was retro-fitted to the implementation because
  the implementation was the right thing and the spec was the
  stale thing (resolves the §6.1 STOP condition from `wt/5a39ff05`).
- **AGENTS.md §12** is updated to add Phase 45 row + bump test count.
  This is an explicitly-allowed §14 modification ("add a newly frozen
  phase to §12") — no CR required.
- **8-event taxonomy** (referenced from `docs/mission_state_machine.md`)
  is frozen and unchanged.

## 6. Tests

| Test surface | Status | Source |
|---|---|---|
| M6.4.A (transport + router + registry + worker + pool + local) | **168/168 PASS** | `1401b81` milestone report |
| M6.4.B.1 (envelope codec) | **39/39 PASS** | `1401b81` milestone report |
| M6.4.B.2 (RemoteTransport exhaustive) | **56/56 PASS** | `337ca64` milestone report |
| M6.4.B code-completion (REMOTE_PREFERRED + task tracking + A-1 AST) | **23/23 PASS** | `0e1b593` milestone report |
| M6.4.C (LeaderElection — 14 classes) | **33/33 PASS** | `fff4daa` milestone report |
| Full repo `pytest` (M6.4 sub-stream cumulative) | **2041/2041 PASS + 2 skipped + 0 failed** | this session, 2026-07-11 19:50 NPT, 166.83s wall |
| Coverage | **91.00%** (target ≥ 80% met; security-relevant modules 100%) | this session |
| `ruff format --check` (M6.4 touched files) | **PASS** | per milestone reports |
| `ruff check` (M6.4 touched files) | **PASS** | per milestone reports |
| `mypy --strict` (M6.4 production files) | **PASS** (12 in M6.4.A; 2 in M6.4.B.2; 2 in M6.4.C) | per milestone reports |
| Architecture Linter + DGV | **PASS** | per `.ai/QUALITY_STATUS.md` |
| A-1 invariant AST inspection | **PASS** | `test_distributed_router_remote_preferred.py::TestA1NoConcreteTransportImport` + static `leader_election.py` |

**Post-merge full-suite regression on `main`:** required per
`AGENTS.md §10` and `.ai/NEXT_ACTION.md` step 6. Expected result:
**2041 passed / 2 skipped / 0 failed** (identical to `phase45/transport`
since the merge is additive — no new test changes, no frozen
interface changes, no behavioral changes on `main` paths).

## 7. Quality Gates

| Gate | Status | Source |
|---|---|---|
| `ruff format --check` on M6.4 touched files | **PASS** | per milestone reports |
| `ruff check` on M6.4 touched files | **PASS** | per milestone reports |
| `mypy --strict` on M6.4 production files | **PASS** | per milestone reports |
| `pytest tests/ -q` (full repo, M6.4 sub-stream) | **PASS** (2041 + 2 skipped + 0 failed) | this session |
| Coverage on M6.4 production files | **≥ 80%** (security-relevant 100%) | per milestone reports |
| Architecture Linter | **PASS** (no layer-direction violations) | per `.ai/QUALITY_STATUS.md` |
| Dependency Graph Validator (DGV) | **PASS** (no circular imports, no layer-reversal) | per `.ai/QUALITY_STATUS.md` |
| A-1 invariant (DistributedRouter / LeaderElection speak only to MissionTransport Protocol) | **PASS** (AST-verified + static) | per milestone reports |
| No active STOP conditions | **PASS** (AGENTS.md §6) | per `.ai/QUALITY_STATUS.md` |
| Architect approval | **AWAITING** (per AGENTS.md §1 rank-5 → rank-2) | this report |

## 8. Rollback

| Rollback point | What it reverts | Risk |
|---|---|---|
| **(this commit, docs only)** | Reverts the AGENTS.md + dashboard + release doc refresh on `phase45/transport` | **None** — docs only; merge commit can still proceed without this refresh |
| **`7abfe19` (one back)** | Reverts the post-M6.4.C .ai/ bookkeeping on `phase45/transport` | **None** — state files only; the M6.4 work is unchanged |
| **`fff4daa` (M6.4.C, two back)** | Reverts the LeaderElection state machine (STRETCH) | **Low** — STRETCH per plan §3, M6.4 sub-stream is still complete without it |
| **`0e1b593` (M6.4.B code-completion, three back)** | Reverts REMOTE_PREFERRED + WorkerRegistry task tracking + envelope bug fix | **Medium** — REMOTE_PREFERRED would raise `NotImplementedError` again; M6.4.B would be partial. NOT recommended unless the bug fix is shown to cause a regression (it shouldn't — the fix produces the same on-wire bytes the codec was always supposed to produce). |
| **`7e53c69` (governance retrofit, four back)** | Reverts spec v1.2 / plan v1.1 / CR-4 / state machine | **HIGH** — re-opens the AGENTS.md §6.1 STOP condition (on-disk code without spec). NOT recommended. |
| **`337ca64` (M6.4.B.2, five back)** | Reverts real Redis transport | **HIGH** — M6.4.B reverts to "envelope-only" state; cross-client delivery broken. NOT recommended. |
| **`1401b81` (M6.4.A, six back)** | Reverts the entire M6.4 sub-stream | **HIGH** — reverts 7 commits / +280 net new tests; breaks the transport contract that M6.3 and M6.5 will consume. NOT recommended unless the M6.4 sub-stream has caused a production regression. |

**Recommended rollback target:** none. The M6.4 sub-stream is
additive (new modules + additive DB columns) and all gates pass.
If a regression is reported, the per-commit rollback order is
documented above; in practice, a hotfix branch is preferred over
reverting to a previous `phase45/transport` commit.

**Worst-case rollback target:** `ce8ebdb` (parent of `phase45/transport`).
Reverts the entire M6.4 sub-stream in one revert commit. State at
`ce8ebdb` is the 0.9.4-frozen state + 0.9.5-prep housekeeping
(`31e6897`); the 0.9.4 release tag remains valid.

## 9. Known Issues

### 9.1 `LeaderElection` ↔ `DistributedRouter` integration is not wired (deferred)

M6.4.C ships the `LeaderElection` primitive + 33 tests but does not
wire `LeaderElection` to elect a single active `DistributedRouter`
instance in a multi-leader deployment. The integration is a future
sub-milestone (will land as M6.4.D or roll into M6.5 observability
hooks). Single-DC scope is explicit per spec §10; multi-region is
a 6.6 future goal.

**Action:** none for this release. Tracked as a follow-up sub-milestone.

**Severity:** low. The LeaderElection primitive is independently
useful (test, scale) and the integration is an additive wiring
that does not block the M6.4 sub-stream landing.

### 9.2 `M6.4.C` is STRETCH (per plan §3)

M6.4.C was marked STRETCH in `docs/108_PHASE_45_IMPLEMENTATION_PLAN.md`
§3. The architect chose to land it (33 tests, 412% of plan §3 floor
of ≥ 8). It is not a STOP condition for the v0.10.0-prep merge, but
it does mean M6.4.C is the only STRETCH sub-milestone in Phase 45
that has landed on `main`. Future STRETCH sub-milestones (if any)
should be similarly opt-in by the architect.

**Action:** none for this release. The choice to land STRETCH is
documented in the M6.4.C milestone report (`docs/reports/PHASE45_M6_4_C_REPORT.md`).

**Severity:** low. STRETCH is opt-in by design; M6.4.C is fully
tested and gated.

### 9.3 No `v0.10.0` FINAL tag (deferred)

This release lands the M6.4 sub-stream on `main` but does NOT cut
the `v0.10.0-persistent-autonomous-runtime` tag. The tag is held
until the FINAL gate per plan §3 + §8, which requires ALL Phase 45
sub-milestones (M6.1.B, M6.2.A/B, M6.3.A/B, M6.5.A/B) to pass.

**Action:** none for this release. A separate v0.10.0 FINAL release
doc + tag will be authored once the other sub-milestones land.

**Severity:** low. The `main` branch is mergeable + consumable in
the v0.10.0-prep state; no user is blocked by the missing tag.

### 9.4 `wt/5a39ff05` lineage preservation (not a release issue)

`wt/5a39ff05` is preserved as a branch ref (working tree was already
gone before this work). The M6.1.A work (`2405abf` lifted to
`1401b81` and `e2cd9fc` lifted to `1401b81`) and the auth admin
recovery work (`wt/5432577e`) are out of scope for this release
but remain reachable for future M6.1.B work and any hotfix cherry-pick.

**Action:** none for this release. The branches are preserved per
the "future proof" framing of the 0.9.5-prep housekeeping commit
(`31e6897`).

**Severity:** low. No data loss; refs are intact.

## 10. Deferred Work

| Item | Reason | Target |
|---|---|---|
| Tag `v0.10.0-persistent-autonomous-runtime` | Per Known Issue 9.3; FINAL gate held | After all Phase 45 sub-milestones pass |
| Author `RELEASE_0.10.0_FINAL_*.md` | The FINAL release report | After v0.10.0 tag |
| `LeaderElection` ↔ `DistributedRouter` integration | Per Known Issue 9.1; future sub-milestone | M6.4.D or M6.5.B |
| M6.1.B (MissionManager rehydration + kill-resume E2E) | Plan §2 sequence | Separate branch off `wt/5a39ff05` (where M6.1.A already lives) |
| M6.2.A/B (Scheduler + REST endpoints) | Plan §2 sequence | Separate branch off `wt/5a39ff05` |
| M6.3.A/B (Crash recovery + DLQ) | Plan §2 sequence | Separate branch off `wt/5a39ff05` |
| M6.5.A/B (Observability dashboard + WebSocket fanout) | Plan §2 sequence | Separate branch off `wt/5a39ff05` |
| Promote CR_SLUG pattern + 12-section milestone report format to `AGENTS.md` | New conventions established by Releases 0.9.1–0.9.4 + 0.10.0-prep | Architect decision (governance change) |

## 11. Next Release

**Release 0.10.0-prep (this) — Phase 45 M6.4 Sub-Stream**

This release. See the 12 sections above.

**Release 0.10.0 FINAL (proposed) — Phase 45 FULL**

The next feature release. Will require its own FINAL release report
+ the `v0.10.0-persistent-autonomous-runtime` tag. Triggered when
M6.1.B + M6.2.A/B + M6.3.A/B + M6.5.A/B all pass individually +
the FINAL gate (full quality gate + walkthrough + AGENTS.md §12
bump) clears. Not yet scoped; the order of sub-milestone pickup is
the architect's call per AGENTS.md §1.

**Release 0.9.4 (already shipped) — Runtime Hotfixes**

0.9.4 SHIPPED on `main` at `ce8ebdb` (CR-002 + CR-003 + CR-004 +
CR-005). Tag at the next natural release boundary; not blocked
by 0.10.0-prep.

---

*Awaiting architect approval per AGENTS.md §1 rank-5 → rank-2: "An
agent MUST NOT proceed to the next milestone without explicit
architect approval." Per the release-boundary push policy (2026-07-10
user profile), the M6.4 sub-stream is mergeable on `main` once the
post-merge full-suite regression passes.*

*Cross-reference: this release is the first prep-tagged release in
the JARVIS release history. It establishes the v0.10.0-prep
pattern (sub-stream lands + FINAL held) that future Phase 45
sub-milestone releases will follow.*
