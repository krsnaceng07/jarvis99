# BUILD CACHE

*Rule: If the changed file is not related to build tools, do NOT run them again. Verify against the `Last *` field below and skip the rebuild.*

**Last Ruff:** PASS (post-0.9.4 on `ce8ebdb`, 2026-07-11 16:47 NPT; all 9 production files in the unpushed range clean)
**Last Mypy:** PASS (post-0.9.4 on `ce8ebdb`, 2026-07-11 16:47 NPT; 6 production files in the unpushed range, 0 errors)
**Last Pytest:** PASS (post-0.9.4 on `ce8ebdb`, 2026-07-11 16:47 NPT; full suite: 1761 passed, 2 skipped, 0 failed in 111.7s)
**Coverage:** 91.00% (target ≥80% met; last full coverage run was 2026-07-11 16:47 NPT)

**Build cache invalidation rules:**

- Change in `pyproject.toml` → invalidate all (ruff config, mypy config, pytest config may all have changed)
- Change in `core/skills/*` (Phase 18, 41) → invalidate `tests/test_skill_*.py`; reuse other test cache
- Change in `core/runtime/persistence_db.py` (Phase 26) → invalidate `tests/test_swarm_persistence.py`; reuse other test cache
- Change in `core/security/seed_service.py` (Phase 17) → invalidate the capability-matrix smoke + `tests/test_runtime_fixes.py`; reuse other test cache
- Change in `AGENTS.md` → invalidate nothing (constitution is doc-only)
- Change in `JARVIS_EXECUTIVE_DASHBOARD.md` → invalidate nothing (dashboard is doc-only)
- Change in `.ai/*` → invalidate nothing (state files are doc-only)
- Change in `docs/CR/CR-XXX-*` → invalidate nothing (CR docs are doc-only)

See `.ai/DEPENDENCY_SCOPE.md` for the per-file impact map.
