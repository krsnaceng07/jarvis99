# CHECKPOINT

*Rule: Mark each milestone on completion. DO NOT batch multiple milestones into one checkpoint.*

**Phase 45 / M6.4 — Distributed Execution (`phase45/transport`)**

| Step | Milestone | Commit | Status |
|------|-----------|--------|--------|
| 1 | M6.4.A scaffold (lifted from `wt/5a39ff05` 2405abf) | `1401b81` | ✅ |
| 2 | M6.4.B.1 envelope codec (lifted from `wt/5a39ff05` e2cd9fc) | `1401b81` | ✅ |
| 3 | M6.4.B.2 real Redis transport | `337ca64` | ✅ |
| 4 | M6.4 governance retrofit (spec/plan/CR-4/state machine) | `7e53c69` | ✅ |

**Open / pending (architect decision required):**
- M6.4.B code-completion gap (REMOTE_PREFERRED in router; WorkerRegistry task tracking; remote-preferred test file) — NOT a spec change, just plan-listed deliverables not yet implemented on the branch
- M6.4.C (stretch — leader election + horizontal scaling) — per plan §3 status: STRETCH, deferrable
- M6.1.A/B, M6.2.A/B, M6.3.A/B, M6.5.A/B (other Phase 45 sub-milestones) — separate branches when picked up

**Other 2026-07-11 milestones (on `main`):**
- 0.9.4 SHIPPED at `ce8ebdb`
- 0.9.5-prep housekeeping at `31e6897` (refreshed .ai/, fixed AGENTS.md §12, pruned worktrees)
