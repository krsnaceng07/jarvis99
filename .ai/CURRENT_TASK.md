# CURRENT TASK

**Goal:** No active task. 0.9.4 release is SHIPPED to `origin/main` at `ce8ebdb` (2026-07-11 16:47 NPT). All CRs (CR-001 through CR-005) are merged. All carry-forward work is closed. All bookkeeping for the 0.9.4 cycle is done.

**Awaiting architect direction for the next move.** Three legitimate next actions are pending the architect's choice:

1. **Cut the `v0.9.4-...` tag** at `ce8ebdb`. Recommended per the release-boundary push policy. No code or doc work needed — the tag is a one-command operation and a release-notes commit.
2. **Start Phase 45 (Persistent Autonomous Runtime, Goal #6) build work.** Pre-work exists on branch `wt/5a39ff05` (M6.4.B.1 — TransportEnvelope Protocol + EnvelopeV1 codec) and `wt/5432577e` (auth admin recovery). Both branches are currently orphaned (not merged to main; the working trees are gone). Architect decision: cherry-pick, merge, or start fresh.
3. **Address other latent housekeeping.** Out-of-scope items in the carry-forward included: replacing the optimistic-locking check with `SELECT ... FOR UPDATE` (Postgres-specific, would unfreeze Phase 26), refactoring `DbSwarmPersistence` to a Unit-of-Work pattern, expanding the capability-matrix probe set. All candidates for a separate "0.9.5 cleanup" cycle.

**Files Allowed (for any task that does start):**
- (per-task) — see the per-task CR doc, if any, for the allowed-modification list
- JARVIS_EXECUTIVE_DASHBOARD.md (READ — for state)
- .ai/PROJECT_STATE.md (READ — for state)
- AGENTS.md (READ — for authority)

**Files Forbidden (carried over from prior cycles):**
- Core business logic engines (frozen).
- Frozen interface modules (see `.ai/FREEZE_LEDGER.md`).
- The `wt/5432577e` and `wt/5a39ff05` branches — DO NOT cherry-pick or merge without architect approval (their working trees are gone, only branch refs remain).

**Success Criteria:**
- (next move TBD per architect)
