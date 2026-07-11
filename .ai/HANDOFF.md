# HANDOFF NOTE

**Current Milestone:** 0.9.4 release — SHIPPED to `origin/main` at `ce8ebdb` (2026-07-11 16:47 NPT). All CRs (CR-001 through CR-005) merged. 1761 tests pass, 0 flakes, 91% coverage.

**Finished:**

- Workflow v3.1 Infrastructure (FROZEN, never modified since)
- Milestone M5.5.2 — Dependency Graph Validator (FROZEN, 179 tests)
- Milestone M5.5.1 — Architecture Linter (FROZEN, 118 tests)
- Phases 1-44 (all FROZEN; Phase 44 is the latest, v1.1 per CR-001)
- 0.9.3 v2 release (tagged `v0.9.3-platform-runtime-stabilization-v2` at `a0e2c2a`)
- 0.9.4 release (SHIPPED to `origin/main`; no premature hotfix tag cut)

**Current Issue:**

None. The 0.9.4 cycle is closed. The next cycle is the architect's choice — see `.ai/TASK_QUEUE.md` for the three options.

**Next Agent Instructions:**

- DO NOT edit workflow files (`.claude/skills/*`, the `.ai/` architecture).
- DO NOT cherry-pick or merge from `wt/5432577e` or `wt/5a39ff05` without explicit architect approval. Both branches' working trees are gone; only the branch refs and their commits remain in the object store. The pre-work on `wt/5a39ff05` (TransportEnvelope Protocol, M6.4.B.1) is real Phase 45 work but is not approved, tested, or spec'd.
- DO NOT cut the `v0.9.4-...` tag without explicit architect approval. The release-boundary push policy defers the tag to the natural release boundary; only the architect can override that.
- DO NOT modify `AGENTS.md` §12 except to add newly frozen phases (per §14).
- When the architect picks the next move (cut tag, start Phase 45, or start housekeeping), follow `.ai/NEXT_ACTION.md` and the appropriate spec/lifecycle document per `AGENTS.md` §5.
- The standard 5-step build loop (per AGENTS.md §5) applies to any new code task: Approved Spec → Implementation Plan → Approval → Task Checklist → Milestones → Final Quality Gate → Walkthrough → Freeze.
