# TASK QUEUE

**Branch:** `main` (HEAD `0b9f1bf` — M6.4 sub-stream MERGED 2026-07-11 20:03 NPT)
**Status:** M6.4 sub-stream CLOSED. All 7 M6.4 sub-milestones (A + A report lift + B.1 + B.2 + governance + B code-completion + C) are merged and pass their gates. Post-merge full-suite regression: 2041 passed / 2 skipped / 0 failed.
**Remaining:** Awaiting architect decision on the next Phase 45 sub-milestone.

**Decisions on the table (NOT in queue until architect calls one):**

1. **M6.1.B — Rehydration + kill-resume E2E** — open a fresh branch off `wt/5a39ff05` (where M6.1.A already lives). Next required foundational sub-milestone per `docs/108_PHASE_45_IMPLEMENTATION_PLAN.md` §2. Estimated: 1-2 milestones, ~250 LoC + 15-20 tests, 1-2 commits.

2. **M6.3.A — MissionRecoveryManager + orphan detection + replay** — open a fresh branch off `wt/5a39ff05`. Crash-recovery milestone. Estimated: 1 milestone, ~200 LoC + 12-15 tests, 1 commit.

3. **M6.2.A — ScheduledMissionDispatcher + triggers table** — open a fresh branch off `wt/5a39ff05`. Scheduler milestone. Estimated: 1 milestone, ~150 LoC + 10-12 tests, 1 commit.

4. **M6.5.A — Mission dashboard views + REST endpoint** — open a fresh branch off `wt/5a39ff05`. Observability milestone. Estimated: 1 milestone, ~120 LoC + 8-10 tests, 1 commit.

5. **Push `main` → `origin/main`** — ✅ DONE 2026-07-11 20:25 NPT. 11-commit fast-forward, no force, no divergence.

6. **Hold all sub-milestones; start FINAL v0.10.0 prep** — FINAL gate is HELD until M6.1.B + M6.2.A/B + M6.3.A/B + M6.5.A/B all pass per plan §8 STOP. So FINAL cannot close until at least the foundational sub-milestones land.

**Next up once architect calls a move:** See `NEXT_ACTION.md` for step-by-step.
