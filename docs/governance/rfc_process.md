# RFC Process — Meta-Workflow

**Status:** PROPOSED (binding from Phase 20 onwards; recommended for any major post-M6 work)
**Date:** 2026-07-03
**Authority:** AGENTS.md §1, §5, §6, §8
**Related:** ARB, DRG, Pre-Milestone Gate, Phase Specification

---

## 1. Purpose

The **Request for Comments (RFC)** process is a **meta-workflow** that sits *above* phases. It exists to ensure that major features (a new phase, a new subsystem, a cross-cutting concern) receive broad engineering scrutiny **before** a phase spec is even drafted.

**Rule:** Any feature that will become a new **Phase** (e.g. Phase 20 Agent Runtime, Phase 22 Workflow Engine) MUST go through the RFC process. Smaller features inside an existing phase do not need an RFC — they go through the standard phase + milestone + ARB/DRG path.

---

## 2. RFC Workflow (12 Stages)

```
1. Idea
   ↓
2. RFC Draft
   ↓
3. Internal Review (small group, 1-2 weeks)
   ↓
4. Public Comment Period (broader team, 2-4 weeks)
   ↓
5. RFC Revision (incorporate feedback)
   ↓
6. Approval (architect + stakeholders)
   ↓
7. Specification (draft phase spec)
   ↓
8. ADR (record architectural decisions made during spec)
   ↓
9. Spec Freeze
   ↓
10. Implementation Plan
   ↓
11. Milestones (each goes through Pre-Milestone Gate)
   ↓
12. Implementation → Audit → Phase Freeze
```

This is **not** a faster process than the existing one — it is a **broader** process. The output of an RFC is an *approved specification*; the implementation follows the standard phase workflow.

---

## 3. When an RFC Is Required

| Change Type | RFC Required? | Reason |
|---|---|---|
| **New Phase** (e.g. Phase 20 Agent Runtime) | YES | New subsystem; multi-milestone; long-lived |
| **New layer** in the architecture | YES | Affects dependency direction |
| **New cross-cutting concern** (auth, encryption, rate-limit) | YES | Affects every subsystem |
| **New external dependency** (DB engine, queue, third-party API) | YES | Operational impact |
| **Major refactor** of an existing phase | YES | Could affect public interfaces |
| **New milestone within existing phase** | NO | Use Pre-Milestone Gate |
| **New API endpoint** | NO | Use Pre-Milestone Gate |
| **Bug fix, perf tweak, doc update** | NO | Standard review process |

---

## 4. RFC Template

Each RFC is filed as `RFC-YYYY-NNN-<short-name>.md` in `docs/rfc/`.

```markdown
# RFC-YYYY-NNN — <Feature Title>

**Status:** DRAFT | IN-REVIEW | APPROVED | REJECTED | WITHDRAWN | SUPERSEDED
**Date:** YYYY-MM-DD
**Author(s):** <names>
**Stakeholders:** <teams affected>

## Summary
<2-3 sentence summary>

## Motivation
<Why is this needed? What problem does it solve?>

## Detailed Design
<Architecture, components, interfaces, data flow>

## Alternatives Considered
| Alternative | Why Rejected |
|---|---|
| ... | ... |

## Drawbacks
<What are the downsides? Risks? Costs?>

## Open Questions
<Unresolved issues; need feedback>

## Future Work
<What does this enable later?>

## References
<Links to prior art, ADRs, specs>

## Discussion
<Comment log, captured inline>

## Decision
<Recorded when status moves to APPROVED or REJECTED>

## Sign-off
| Role | Name | Date |
|---|---|---|
| Author | | |
| Architect | | |
| Stakeholders | | |
```

---

## 5. RFC States

| State | Meaning | Allowed Transitions |
|---|---|---|
| **DRAFT** | Author writing | → IN-REVIEW, WITHDRAWN |
| **IN-REVIEW** | Open for comment | → REVISION, APPROVED, REJECTED, WITHDRAWN |
| **REVISION** | Author updating based on feedback | → IN-REVIEW, WITHDRAWN |
| **APPROVED** | Specification may be drafted | → SUPERSEDED |
| **REJECTED** | Will not pursue | (terminal) |
| **WITHDRAWN** | Author abandoned | (terminal) |
| **SUPERSEDED** | Replaced by a later RFC | (terminal) |

---

## 6. RFC for Major JARVIS OS Features (Backlog)

This section is the **RFC backlog** — features that should go through the RFC process when capacity allows.

| RFC | Title | Phase | Priority | Status |
|---|---|---|---|---|
| RFC-2026-001 | Agent Runtime (LLM-in-the-loop with bounded tool calls) | 20 | High | NOT-STARTED |
| RFC-2026-002 | Workflow Engine (DAG-based, durable, retryable) | 22 | High | NOT-STARTED |
| RFC-2026-003 | Reasoning Engine (chain-of-thought, ReAct, planner-executor) | 23 | Medium | NOT-STARTED |
| RFC-2026-004 | Browser Engine (Playwright-based, headless) | 24 | Medium | NOT-STARTED |
| RFC-2026-005 | Desktop Controller (mouse, keyboard, screen capture) | 25 | Medium | NOT-STARTED |
| RFC-2026-006 | Voice Subsystem (Whisper STT, ElevenLabs TTS) | 26 | Low | NOT-STARTED |
| RFC-2026-007 | Vision Subsystem (CLIP, OCR, scene understanding) | 27 | Low | NOT-STARTED |
| RFC-2026-008 | Multi-Agent Protocol (inter-agent messaging) | 28 | High | NOT-STARTED |
| RFC-2026-009 | Mobile Companion (iOS/Android clients) | 29 | Low | NOT-STARTED |
| RFC-2026-010 | Cloud Sync (encrypted, conflict-resolved) | 30 | Low | NOT-STARTED |

**M6 (Knowledge Graph) does NOT need an RFC** — it is a milestone within an existing frozen phase (Phase 19). The Pre-Milestone Gate, ARB, DRG, and freeze artifacts are sufficient.

---

## 7. RFC vs Phase Spec vs ADR

| Document | When | Author | Audience | Lifetime |
|---|---|---|---|---|
| **RFC** | Before spec | Feature proposer | Engineers, architects | Months (during design) |
| **Phase Spec** | After RFC approval | Spec author | Implementers, QA | Years (frozen) |
| **ADR** | During/after spec | Architect or spec author | Future maintainers | Years (frozen) |
| **EDL entry** | During implementation | Anyone | On-call, current team | Months (reviewable) |

---

## 8. Versioning

- v1.0 (2026-07-03): RFC process introduced. Backlog of 10 future features catalogued.
