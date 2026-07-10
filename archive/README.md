# Archive — Legacy Documentation

**Archived on:** 2026-07-10
**Reason:** Documentation governance cleanup. These files were either:
- Parallel/competing governance systems superseded by `AGENTS.md`
- Model-specific adapter artifacts no longer in active use
- Methodology references for workflows not actually deployed in JARVIS

All archived files are **recoverable from git history**. To restore:
```bash
git restore <path>
```

---

## legacy_governance/.antigravity/ — 9 files

**Source:** `E:\jarvis\.antigravity\`

**Files:**
- ARCHITECTURE_RULES.md
- ENGINEERING_CONSTITUTION.md
- GOVERNANCE_RULES.md
- IMPLEMENTATION_PROTOCOL.md
- PHASE_EXECUTION_PROTOCOL.md
- PROMPT_TEMPLATE.md
- QUALITY_GATES.md
- REVIEW_PROTOCOL.md
- SYSTEM_CONSTITUTION.md

**Reason archived:**
- Parallel governance system mirroring `AGENTS.md` and `docs/00_PROJECT_CONSTITUTION.md`
- `GOVERNANCE_RULES.md` line 9 explicitly claimed `AGENTS.md & System Constitutions` as equal at Rank 2 — a direct SSOT violation
- Frozen phase list outdated (Phase 1-19 only — actual project is at Phase 43 per `.ai/PROJECT_STATE.md`)
- "Antigravity" tooling (Cursor's pre-rebrand name) no longer in active use

**Canonical replacement:** `AGENTS.md` + `docs/00_PROJECT_CONSTITUTION.md` + `docs/31..49_*_STANDARD.md`

---

## legacy_methodology/ — 2 files

**Source:** `E:\jarvis\PROJECT_RULES.md`, `E:\jarvis\GSD-STYLE.md`

**Files:**
- PROJECT_RULES.md (GSD canonical rules)
- GSD-STYLE.md (style/conventions reference)

**Reason archived:**
- PROJECT_RULES.md describes a SPEC → PLAN → EXECUTE → VERIFY → COMMIT workflow but JARVIS does not actually use this — `.gsd/STATE.md`, `.gsd/ROADMAP.md`, `.gsd/SPEC.md` do not exist
- Actual JARVIS state tracking is in `.ai/PROJECT_STATE.md`, `.ai/CURRENT_TASK.md`, `.ai/CHECKPOINT.md`
- PROJECT_RULES.md self-declares as "Single Source of Truth" — directly competes with `AGENTS.md §0` for canonical authority (AGENTS.md wins per §1 Rank 2)
- GSD-STYLE.md was a companion document — loses its anchor once PROJECT_RULES.md is archived

**Canonical replacement:** `AGENTS.md §5` (Implementation Lifecycle) + `docs/44_GIT_WORKFLOW.md` + `docs/45_BRANCHING_STRATEGY.md`

---

## legacy_tools/.claude/ — 3 files

**Source:** `E:\jarvis\.claude\skills\`

**Files:**
- skills/build-skill/SKILL.md
- skills/review-skill/SKILL.md
- skills/spec-skill/SKILL.md

**Reason archived:**
- Small (700-800 bytes each), likely Claude-specific stubs
- Conceptually duplicates of `.agents/skills/{executor,verifier,spec-skill}/SKILL.md` which are the active skill set
- `.claude/` directory not referenced by any active tooling

**Canonical replacement:** `.agents/skills/executor/SKILL.md`, `.agents/skills/verifier/SKILL.md`, `.agents/skills/spec-skill/SKILL.md`

---

## legacy_adapters/ — 1 file

**Source:** `E:\jarvis\adapters\GEMINI.md`

**Files:**
- adapters_GEMINI.md (renamed for path disambiguation)

**Reason archived:**
- Content referenced deprecated `PROJECT_RULES.md` and Antigravity tooling
- Active Gemini adapter is `.gemini/GEMINI.md` (different file, different path)

**Canonical replacement:** `.gemini/GEMINI.md`

---

## Recovery Instructions

If any archived file is needed:

```bash
# Restore single file
git restore .antigravity/SYSTEM_CONSTITUTION.md

# Restore entire directory
git restore .antigravity/
```

After restore, the file will appear in its original location. To permanently delete:
```bash
git rm <path>
git commit -m "chore(docs): remove legacy <name>"
```

---

*Audit lead: Mavis*
*Phase A — Documentation Governance Audit v1.0*