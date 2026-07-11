# AGENT STATE

**Current Roles (post-0.9.4):**

- **Architect:** User (the JARVIS project owner). Approves, rejects, freezes, and sets release boundaries. Per the user profile memory, the user has been acting as the JARVIS architect across v0.9.0-rc2 and Goal #6 (Phase 45) work. Decisions on tag strategy, branch salvage (wt/5432577e, wt/5a39ff05), and the next move direction come from the architect.
- **Orchestrator:** Mavis (mavis / `mvs_*` session tree). Coordinates the multi-agent workflow, runs the 5-step build loop, owns the carry-forward bookkeeping, drafts CRs, and pushes to `origin/main` after explicit architect approval. Root session ID at session start.
- **Verifier / Reviewer:** Spawned on-demand via `mavis communication send --command spawn` (verifier-only channel). Reviews deliverables against the spec and the quality gate. Never writes code.
- **Specialist sub-agents:** Loaded on-demand via the `mavis-team` skill when the task is large enough to warrant a team. For small bookkeeping like the 0.9.4 carry-forward, the orchestrator handles it directly.

**Historical roles (no longer in use, retained for traceability):**

- The pre-Goals-#1-5 era used "OpenAI Architect, Claude Spec Agent, Claude Build Agent, Gemini Reviewer" as role labels (see the pre-refresh `AGENT_STATE.md` from `b3a1e70`). That role split has been replaced by the orchestrator pattern above; the Mavis tree handles Spec, Plan, Build, and Review internally or via the `mavis-team` skill.
