# TASK QUEUE

**Total Steps:** 3
**Completed:** 0
**Remaining:** 3 (all architect-decision-gated)

**Next up in queue (architect chooses the order):**

1. **Cut 0.9.4 tag at `ce8ebdb`** (recommended: defer to natural boundary, but available on request)
   - Sub-steps: (a) confirm tag name; (b) `git tag -a v0.9.4-... ce8ebdb -m "..."`; (c) `git push origin v0.9.4-...`; (d) write `docs/releases/RELEASE_0.9.4_*.md` notes; (e) commit + push notes; (f) update dashboard
2. **Audit Phase 45 pre-work branches** (`wt/5a39ff05`, `wt/5432577e`)
   - Sub-steps: (a) `git log wt/5a39ff05 --oneline -20` to review; (b) `git log wt/5432577e --oneline -20` to review; (c) decide cherry-pick vs. fresh; (d) if cherry-pick: cut a fresh branch off `ce8ebdb`, cherry-pick the relevant commits, run gate, push; (e) if fresh: proceed with the standard spec → plan → implement → freeze lifecycle
3. **Start the 0.9.5 cleanup cycle** (housekeeping backlog)
   - Sub-steps: (a) write a CR-006 doc covering the Unit-of-Work refactor, the Postgres upgrade, and the capability-matrix expansion; (b) get architect sign-off; (c) implement per the CR's §4
