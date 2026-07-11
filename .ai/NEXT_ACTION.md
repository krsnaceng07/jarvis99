# NEXT ACTION

**Step-by-step (M6.4 sub-stream merge to `main`):**

1. Read AGENTS.md §1 rank-5 → rank-2 transition rule + `docs/44_GIT_WORKFLOW.md` (merge strategy + conventional commit format).
2. Refresh AGENTS.md §12 row 45: change from "🔨 IN DEVELOPMENT on `phase45/transport`" to "🟨 STAGED for v0.10.0 (M6.4 sub-stream landed, awaiting FINAL gate)" and bump the test count to 2041.
3. Refresh JARVIS_EXECUTIVE_DASHBOARD.md: Phase 45 row reflects M6.4 sub-stream closure.
4. Add a CHANGELOG entry: "v0.10.0-prep / M6.4 sub-stream — Distributed execution scaffold (MissionTransport + LocalTransport + RemoteTransport over Redis + DistributedRouter + EnvelopeV1 + LeaderElection); spec v1.2 FROZEN-amended under CR-1/2/3/4; 7 commits on `phase45/transport`; 2041 tests passing".
5. On `main` (architect's session): `git merge --no-ff phase45/transport` (preserves the M6.4 sub-stream as a named branch in the merge commit). Merge commit message: `chore(release): merge M6.4 distributed execution to main (Phase 45 v0.10.0-prep)`.
6. Run full-suite regression on `main` post-merge: `pytest tests/ -q --tb=short -p no:cacheprovider` — expect 2041 passed / 2 skipped / 0 failed.
7. Per AGENTS.md §10, emit a final post-merge summary message and STOP (do not auto-pick-up the next Phase 45 sub-milestone).

**Step-by-step (alternative — if architect pivots to M6.1.B, M6.3.A, M6.5.A, M6.2.A/B, or main housekeeping):**

- For M6.4 merge + M6.1.B in parallel: do the merge first (steps above), then open the M6.1.B branch off `main` (post-merge) so M6.1.B doesn't carry M6.4 work in its history.
- For M6.1.B without M6.4 merge: open a fresh branch off `wt/5a39ff05` lineage (where M6.1.A already exists). Do NOT branch off `phase45/transport`.
- For pivot to a different sub-milestone entirely: wait for architect decision. Do not start new work without explicit go.

**Architect decision required (per AGENTS.md §1 rank-5 → rank-2):**

- ✅ **Approve merge of `phase45/transport` → `main`** — M6.4 sub-stream lands on main; Phase 45 row 45 in AGENTS.md §12 becomes STAGED.
- **Hold merge, pivot to M6.1.B in parallel** — M6.4 work stays on the branch; M6.1.B opens off `wt/5a39ff05`. (Per the user's "release-boundary push" preference, the merge path is recommended.)
- **Hold merge + M6.4.C follow-up** — the M6.4.C ↔ DistributedRouter integration is a future sub-milestone; do not block the merge on it.
