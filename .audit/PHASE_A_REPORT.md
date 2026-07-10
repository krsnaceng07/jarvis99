# PHASE A — Documentation Inventory Report

**Project:** JARVIS
**Workspace:** `E:\jarvis`
**Audit Date:** 2026-07-10
**Total .md files:** 292
**Total size:** 1,307 KB

---

## Executive Summary

JARVIS project has **292 .md files**, of which:

| Category | Count | Action |
|----------|-------|--------|
| KEEP (frozen/canonical/boot) | 76 | Already identified, no action |
| TBD (need dependency + duplicate check) | 193 | Phase B-D analysis |
| ARCHIVE_CANDIDATE (reports) | 21 | Phase E review |
| REVIEW (competing authorities) | 2 | Manual architect decision |

**3 major SSOT violations detected** requiring architect decision.

---

## 🚨 Critical Finding 1: `.antigravity/` is a parallel governance system

**9 files** in `.antigravity/` mirror AGENTS.md + docs/ standards:

| File | Conflicts with |
|------|----------------|
| `SYSTEM_CONSTITUTION.md` | `AGENTS.md §0`, `docs/00_PROJECT_CONSTITUTION.md` |
| `GOVERNANCE_RULES.md` | `AGENTS.md §1` (authority ranking), §6 (STOP protocol) |
| `ENGINEERING_CONSTITUTION.md` | `AGENTS.md §7` (invariants), `docs/33_CODE_STANDARD.md` |
| `PROMPT_TEMPLATE.md` | `AGENTS.md §11`, `docs/09_PROMPT_CONSTITUTION.md` |
| `IMPLEMENTATION_PROTOCOL.md` | `AGENTS.md §5` (lifecycle) |
| `PHASE_EXECUTION_PROTOCOL.md` | `AGENTS.md §2` (boot sequence) |
| `REVIEW_PROTOCOL.md` | `AGENTS.md §6` (review gates) |
| `QUALITY_GATES.md` | `docs/47_QUALITY_GATES.md` |
| (1 more — to be enumerated) | — |

**Evidence:** `.antigravity/GOVERNANCE_RULES.md` line 9 explicitly claims `AGENTS.md & System Constitutions` are **equal at Rank 2** — a direct SSOT violation.

**Outdated:** The same file (line 24) lists frozen phases only through Phase 19 — current state per `PROJECT_STATE.md` is **Phase 43**.

**Recommendation:** **ARCHIVE `.antigravity/` entirely** — content is either redundant with AGENTS.md/docs/ or outdated. Move to `archive/.antigravity/` with a README explaining why.

---

## 🚨 Critical Finding 2: `PROJECT_RULES.md` vs `AGENTS.md` competing authority

Both files self-declare as canonical:

| File | Self-declared role |
|------|-------------------|
| `AGENTS.md` §0 | "single canonical entry-point for ANY agent" |
| `PROJECT_RULES.md` line 3 | "Single Source of Truth for the Get Shit Done methodology" |

**AGENTS.md has higher authority** per `AGENTS.md §1` (Rank 2: "Agent Constitution"). PROJECT_RULES.md is **Rank 5 or below** as a methodology reference.

**Conflict zones:**
- SPEC→PLAN→EXECUTE→VERIFY→COMMIT (PROJECT_RULES) vs Plan→Freeze→Validate→Archive (AGENTS.md §5)
- Adapter pattern (PROJECT_RULES) vs hardcoded canonical (AGENTS.md)

**Recommendation:** **Resolve in favor of AGENTS.md.** Either:
- (a) Refactor `PROJECT_RULES.md` into `docs/methodology/GSD.md` (subordinate reference), or
- (b) Archive `PROJECT_RULES.md` entirely (its unique content is small — search-first, wave execution, commit conventions — most of which is already in AGENTS.md §5.1 / §11)

---

## 🚨 Critical Finding 3: ADR-001 numbering collision

`docs/adr/` and `docs/architecture/adrs/` both contain files named `ADR-001*` with **different content**:

```
docs/adr/ADR-001-Knowledge-Graph-Storage.md       (4.63 KB)
docs/adr/ADR-001_EventBus.md                       (1.33 KB)
docs/architecture/adrs/ADR-001-memory-storage.md  (4.05 KB)
```

Same collision pattern for ADR-002, 003, 004, 005.

**Recommendation:**
- Pick canonical ADR location: **`docs/architecture/adrs/`** (consistent with `docs/architecture/*_FREEZE.md` pattern)
- For each duplicate, determine which is the active decision
- Move active one to canonical path with consistent naming
- Move deprecated one to `archive/adr/`

---

## Distribution Analysis

```
docs/                          188 files
├── adr/                        13 files (numbering collision detected)
├── architecture/               15 files (FREEZE files - critical)
├── contracts/                   4 files
├── decisions/                   1 file
├── diagrams/                    0 files
├── failure/                     1 file
├── governance/                 10 files
├── observability/               1 file
├── performance/                 1 file
├── phases/phase19/              3 files
├── reports/                    22 files (ARCHIVE candidates)
└── (root of docs/)            115 files (mix of standards, phase specs, plans)

.ai/                            18 files (boot sequence — mostly KEEP)
.gsd/                           28 files (planning artifacts)
.agent/                         27 files (workflows)
.agents/                        11 files (skills)
.antigravity/                    9 files (PARALLEL GOVERNANCE — SSOT violator)
.claude/                         3 files (Claude-specific skills — overlap with .agents/)
.gemini/                         1 file (GEMINI.md)
(root)                           4 files (AGENTS.md, GSD-STYLE.md, JARVIS_EXECUTIVE_DASHBOARD.md, PROJECT_RULES.md)
```

---

## Lifecycle Distribution (Phase A scoring)

| Lifecycle | Count | Action |
|-----------|-------|--------|
| FROZEN | 70 | Locked, never modify |
| ACTIVE | 199 | In use, review for need |
| ARCHIVED | 21 | Move to archive/ |
| REVIEW | 2 | Architect decision |

---

## Phase A Top Cleanup Targets

| # | Target | Action | Risk |
|---|--------|--------|------|
| 1 | `.antigravity/` (9 files) | ARCHIVE | Low (redundant, outdated) |
| 2 | `PROJECT_RULES.md` | REFACTOR or ARCHIVE | Medium (governance overlap) |
| 3 | ADR duplicates (5+ pairs) | CONSOLIDATE | Medium (need to verify active decision) |
| 4 | `GEMINI.md` (2 files) | CONSOLIDATE | Low |
| 5 | `docs/PHASE_3X_IMPLEMENTATION_PLAN.md` (5 files at docs/ root) | MOVE to `docs/phases/` | Low (organizational) |
| 6 | `.claude/skills/*` (3 files) | EVALUATE | Low (may overlap with .agents/skills) |

---

## Next Phase Requirements

To complete the audit, the following are needed (Phase B-D):

1. **Phase B — Dependency Graph:** Cross-reference scan — which files reference which (impact analysis for any merge/archive)
2. **Phase C — Duplicate Detection:** Content similarity analysis on ACTIVE files
3. **Phase D — Authority Matrix:** Compile final authority ranking per topic
4. **Phase E — Review & Approval:** Architect decision on top 6 targets

**Estimated time for Phase B-D:** 30-45 minutes (read-only analysis, no file modifications).

**No file has been modified.** This is analysis-only.

---

*Generated: 2026-07-10*
*Audit lead: Mavis*
*Methodology: 7-criteria scoring (Referenced, Frozen, Boot, Runtime, Historical, Duplicate, Usage Score 0-100)*