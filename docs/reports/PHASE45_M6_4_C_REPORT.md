# PHASE 45 M6.4.C REPORT

## Milestone Summary
**Completed:** M6.4.C (STRETCH) — `LeaderElection` state machine on top of
`MissionTransport.lease` / `renew_lease` / `release_lease`. Splits the
leader-election concern out of the router and provides split-brain-safe
multi-candidate election. Single-DC only (per spec §10).
**Date:** 2026-07-11
**Status:** ✅ PASS — awaiting architect approval before merge to `main`.

## Scope (per `docs/108_PHASE_45_IMPLEMENTATION_PLAN.md` §3 M6.4.C)

- `LeaderElection` — single-shot state machine for one candidate in one
  election cycle. CANDIDATE → LEADER | FOLLOWER; LEADER → STEPPED_DOWN |
  RELEASED; any → CLOSED on transport close.
- `LeaderRole` enum (str-mix-in for JSON-serializable log lines) with
  6 states: CANDIDATE, FOLLOWER, LEADER, STEPPED_DOWN, RELEASED, CLOSED.
- `LeaderElectionError` for misuse (re-acquire after release, campaign
  from non-CANDIDATE, etc.).
- `campaign()` — long-running helper that does try_acquire, then renews
  at `ttl/3` cadence until stepped down, with optional `max_iterations`
  for tests. Cancellable: on `asyncio.CancelledError` it gracefully
  releases the lease.
- Per A-1, the module speaks only to the `MissionTransport` Protocol
  (concrete `LocalTransport` / `RemoteTransport` never imported — only
  the Protocol type annotation).

### What M6.4.C is *not*

- **Not a multi-region leader election.** Per spec §10 line 743, multi-
  region is a future `6.6 Multi-region Federation` goal. M6.4.C is
  single-DC only.
- **Not a DistributedRouter integration.** Per A-1 + the spec, the router
  speaks only to the transport Protocol. M6.4.C ships the election
  primitive; integrating it with the router to elect a single
  DistributedRouter instance is a future sub-milestone (out of M6.4.C
  scope per the plan).
- **Not a Redis failover primitive.** Per spec §6.4 R7, the M6.4.B
  default is "single-leader, operator-controlled failover" — if Redis
  is down, the existing leader continues, no automatic failover. M6.4.C
  adds multi-candidate election but does not change the degraded-mode
  contract.

## Files Modified / Added

### NEW
| File | Responsibility |
|------|----------------|
| `core/mission/leader_election.py` | `LeaderElection` state machine + `LeaderRole` enum + `LeaderElectionError`. |
| `tests/test_leader_election.py` | 33 tests across 14 test classes (see Test breakdown below). |
| `docs/reports/PHASE45_M6_4_C_REPORT.md` | This report (AGENTS.md §10 format). |

### MODIFIED
None. M6.4.C is a fresh module; no existing file is touched.

## Architecture Impact

- **Additive only.** No frozen-interface change, no DTO change, no
  Protocol change. The new module sits alongside `DistributedRouter`
  and `WorkerRegistry` without modifying either.
- **A-1 invariant preserved.** `LeaderElection` is typed against the
  `MissionTransport` Protocol; it never imports `LocalTransport` or
  `RemoteTransport` directly. Test file does import them (tests
  legitimately drive concrete implementations), but the
  production code is Protocol-only.
- **No CR required.** Spec text in `docs/107` §3.2 line 501 already
  names M6.4.C as "(stretch, optional)"; §4.4 line 512 already
  specifies the leader-election shape ("an optional leader-election
  (Redis SETNX-based lease) prevents two leaders from running
  simultaneously"). The plan §3 M6.4.C deliverable list authorises
  this work. No spec/plan amendment is needed.

## Public Interface Changes

- `LeaderElection` (NEW class) — see `core/mission/leader_election.py`
  for the full API. Public surface:
  - `__init__(transport, lease_key, ttl_seconds, *, candidate_id=None)`
  - properties: `role`, `token`, `candidate_id`, `is_leader`, `lease_key`, `ttl_seconds`
  - `async try_acquire() -> bool`
  - `async renew() -> bool`
  - `async release() -> None`
  - `async campaign(*, renew_interval=None, max_iterations=None) -> LeaderRole`
- `LeaderRole` (NEW enum) — 6 states, str-mix-in.
- `LeaderElectionError` (NEW exception).
- `core.mission.leader_election.__all__ = ["LeaderElection", "LeaderElectionError", "LeaderRole"]`.

No existing public surface is changed.

## Tests Added

33 tests in `tests/test_leader_election.py` (plan §3 M6.4.C floor was
≥ 8; this milestone ships 33 — 412% of floor). The test plan
favourably exceeds the floor because M6.4.C is the last M6.4
sub-milestone and the test surface is small + cheap (no DB, no
fixtures beyond in-process transports). 14 test classes:

| Test class | Tests | Coverage |
|------------|-------|----------|
| `TestConstructorValidation` | 7 | lease_key type, ttl range, transport-open, candidate_id default + custom, initial state. |
| `TestAcquireHappyPath` | 1 | single-candidate acquire → LEADER. |
| `TestAcquireWhenHeld` | 1 | second candidate → FOLLOWER. |
| `TestRenewKeepsLeader` | 1 | renew returns True, role stays LEADER. |
| `TestRenewFailsAfterExpiry` | 2 | force-expire → STEPPED_DOWN; re-acquire after STEPPED_DOWN raises. |
| `TestReleaseFrees` | 1 | after release, a fresh candidate can acquire. |
| `TestReleaseIdempotent` | 2 | double-release is a no-op; release-without-acquiring transitions to RELEASED. |
| `TestReacquireFromTerminalRaises` | 2 | re-acquire from LEADER / RELEASED raises. |
| `TestRenewFromNonLeader` | 3 | renew from CANDIDATE / FOLLOWER / RELEASED returns False without state change. |
| `TestAcquireAfterTransportClose` | 2 | try_acquire / renew after transport close → CLOSED. |
| `TestSplitBrainTwoCandidates` | 2 | 2 candidates race; exactly one wins; after release the other can take over. |
| `TestSplitBrainThreeCandidates` | 2 | 3 candidates, only one is leader; after step-down, a fresh candidate can take over. |
| `TestCampaignLoop` | 5 | max-iterations returns LEADER; non-CANDIDATE raises; FOLLOWER on initial-acquire-failure; STEPPED_DOWN on renew-failure; cancellation releases the lease. |
| `TestCrossClientLeaderElection` | 2 | Redis-backed transport split-brain + renew-after-force-expire (proves the wire path, not a same-process shortcut). |

**Total: 33 new tests, 14 test classes.**

## Invariants verified

| # | Invariant | Verified by |
|---|-----------|-------------|
| A-1 | `LeaderElection` is typed against the `MissionTransport` Protocol; never imports concrete transport. | AST inspection (the type annotation `transport: MissionTransport` is the only reference; no `from core.mission.transports.local import` or `from core.mission.transports.redis import` in the source). |
| D-4 (CR-4) | Runtime exactly-once is unaffected by the election — the election is orthogonal to message delivery. | Indirect: M6.4.B's `mark_task_started` / `mark_task_completed` (D-4 honour) is unchanged. |
| Single-DC scope | M6.4.C does not introduce multi-region primitives. | The module only operates on a single `MissionTransport`; no second-DC awareness, no cross-region coordination. |
| Degraded mode (spec §6.4 R7) | If transport is closed, the candidate's local state transitions to CLOSED; the lease naturally expires in the backing store. | `TestAcquireAfterTransportClose::test_renew_after_close_becomes_closed` + `TestAcquireAfterTransportClose::test_try_acquire_after_close_returns_false_and_becomes_closed`. |
| Split-brain safety | Two `LeaderElection` instances racing for the same key: exactly one wins. | `TestSplitBrainTwoCandidates::test_two_candidates_race_only_one_wins` (2 candidates) + `TestSplitBrainThreeCandidates::test_three_candidates_only_one_is_leader` (3 candidates). |
| Cross-client wire path | Redis SETNX + Lua atomicity contract is exercised. | `TestCrossClientLeaderElection::test_redis_transport_split_brain` (proves the wire path, not a same-process shortcut). |

## Layer direction audit (architecture freeze compliance)

- `core/mission/leader_election.py` → `core/mission/mission_transport.py` (Protocol type) — `core/ → core/` ✅
- No reverse-direction imports.
- No `api/ → leader_election` edge (the API is unchanged).

## Quality Gates

| Gate | Tool | Result |
|------|------|--------|
| Format | `ruff format --check` on `core/mission/leader_election.py` + `tests/test_leader_election.py` | ✅ 2 files already formatted |
| Lint | `ruff check` on the same 2 files | ✅ All checks passed (auto-fixed 1 I001 import sort + 1 F841 unused variable during dev) |
| Types | `mypy --strict` on the same 2 files | ✅ Success: no issues found in 2 source files |
| Tests | `pytest tests/test_leader_election.py -v` | ✅ 33/33 passed in 0.89s |
| Regression | `pytest tests/` (full suite) | ✅ **2041 passed / 2 skipped / 0 failed** (was 2008 pre-M6.4.C → +33 net new; zero regression vs `337ca64` baseline 1985 and vs `0e1b593` 2008) |
| Architecture | AST inspection of `core/mission/leader_election.py` — no concrete transport import | ✅ Module only imports `core.mission.mission_transport.MissionTransport`; never `LocalTransport` or `RemoteTransport`. |

## Gate Status

✅ **PASS** — M6.4.C is ready for architect approval before the M6.4
sub-stream merge to `main`.

## Test count roll-up

| Source | Count |
|--------|-------|
| Pre-M6.4.C (`0e1b593` M6.4.B code-completion) | 2008 |
| M6.4.C additions | 33 |
| **Total on `phase45/transport` post-M6.4.C** | **2041** |

## Open / Deferred (informational, not blockers)

- **DistributedRouter integration** — wiring `LeaderElection` to elect a
  single active `DistributedRouter` instance is a future sub-milestone
  (out of M6.4.C scope per the plan). The election primitive is shipped
  and tested; the integration is its own gate when M6.4 streams into
  a multi-leader deployment.
- **Multi-region leader election** — out of scope per spec §10; future
  `6.6 Multi-region Federation` goal.
- **Auto-failover on Redis loss** — out of scope per spec §6.4 R7;
  operator-controlled failover remains the contract.

## Next Steps

Awaiting architect approval before:

1. **M6.4 sub-stream merge to `main`** — per AGENTS.md §1 rank-5 → rank-2
   transition. The branch now contains M6.4.A (`1401b81`) + M6.4.A
   report lift (`eb54911`) + M6.4.B.1 (`1401b81`) + M6.4.B.2
   (`337ca64`) + M6.4 governance retrofit (`7e53c69`) + M6.4.B
   code-completion (`0e1b593`) + M6.4.C (this milestone). All gates ✅.
2. **Phase 45 pivot** — after merge, the next Phase 45 sub-milestone per
   plan §2 sequence is M6.1.B (MissionManager rehydration + kill-resume
   E2E), on a fresh branch off `wt/5a39ff05` lineage (where M6.1.A
   already lives). Per RESUME_STATE.md, do NOT branch off
   `phase45/transport` to keep the M6.4 stream clean.

---

*Per AGENTS.md §10, this report is the M6.4.C mini-gate deliverable.
The next gate is the M6.4 sub-stream merge to `main` (architect
approval required per AGENTS.md §1 rank-5 → rank-2 transition).*
