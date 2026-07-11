# TASK QUEUE

**Branch:** `phase45/transport`
**Total Steps:** 4 (M6.4.A + M6.4.B.1 + M6.4.B.2 + governance retrofit)
**Completed:** 4
**Remaining:** Awaiting architect decision (not in queue — branches the next move)

**Decisions on the table (NOT in queue until architect calls one):**

1. **M6.4.B code-completion** — implement REMOTE_PREFERRED in DistributedRouter; add mark_task_started/completed to WorkerRegistry; add `tests/test_distributed_router_remote_preferred.py` (≥ 10 tests). Plan-listed, not a spec amendment; no CR-6 required. Estimated: 1 milestone, ~150 LoC + 10-15 tests, 1 commit.

2. **M6.4.C (stretch)** — leader election (Redis SETNX leases prevent two-leader split-brain) + horizontal scaling acceptance tests. STRETCH per plan §3, deferrable. Estimated: 1 milestone, ~80 LoC + 8 tests, 1 commit.

3. **Pivot to another sub-milestone** — open a new branch off `wt/5a39ff05` (M6.1.A already there) and pick up M6.1.B (rehydration + kill-resume E2E), M6.3.A (recovery manager), M6.2.A (scheduler), or M6.5.A (observability dashboard). Each is a separate work stream.

4. **Merge `phase45/transport` to `main` first** — but the M6.4.A freeze requires recovering the milestone report from `wt/5a39ff05` and walking through the architect sign-off. The 1401b81 + 337ca64 commits do NOT include their own freeze reports.

**Next up once architect calls a move:** See `NEXT_ACTION.md` for step-by-step.
