# Handoff — Change Requests (CRs)

This directory holds **Change Requests (CRs)** per AGENTS.md §8. A CR is the
formal mechanism for proposing changes to frozen sources (§4), for amending the
Plan, or for triggering any spec/plan-vs-code reconciliation.

## Status legend

- `DRAFT` — proposal written by an agent or architect; not yet actioned.
- `APPROVED` — architect-signed; amendments recorded; frozen docs updated.
- `WITHDRAWN` — proposal abandoned (with reason).

## CR numbering convention

- `CR-XXXX_<short-name>.md` — incremental, zero-padded.
- Each CR must include: scope (which frozen doc/interface), rationale, files
  affected, gate test (does it break anything?), approval signature block.

## Index

| CR | Title | Status | Scope |
|----|-------|--------|-------|
| CR-1 | Spec §4.3 line 430 `state=ORPHANED` typo alignment | DRAFT | `docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md` |
| CR-2 | Plan §3 amendments (filename + path typos) — M6.4.A renumbering, `core/mission/` vs `core/runtime/` per spec §3 | DRAFT | `docs/108_PHASE_45_IMPLEMENTATION_PLAN.md` |
| CR-3 | Phase 26 `agent_loop_journals.wave_run_id` additive column (Phase 46 candidate) | DRAFT | `core/runtime/recovery_manager.py` (Phase 26 FROZEN) — additive only |
| CR-4 | Phase 45 spec §6.4 addendum: **D-4** (runtime idempotency — was review D-2) + **D-5** (versioned transport envelope — was review D-3). Resolves labeling collision with already-adopted D-2/D-3 (M6.4.A). | DRAFT | `docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md` §6.4 + `docs/108_PHASE_45_IMPLEMENTATION_PLAN.md` §3 M6.4.B + new `core/mission/transports/envelope.py` |

## Origin

These three CRs originate from the M6.3.A + M6.3.B gate (commit `c4d83da`,
2026-07-08) where the architect delegated approval authority to the agent
(`Mavis`) with explicit "future-proof + safe" mandate. Each CR captures a
**specification drift** already corrected at the code layer via
spec-wins/plan-loses rules (AGENTS.md §1), so the CRs are intended as
documentation alignment rather than behavioral change.
