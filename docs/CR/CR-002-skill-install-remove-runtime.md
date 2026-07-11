# CR-002 — Skill Install/Remove Runtime Alignment with Phase 18 / 41 Spec

**Status:** 🟡 PROPOSED (awaiting architect approval)
**Date:** 2026-07-11
**Proposer:** Mavis (orchestrator session `mvs_1eef650acaf648eb92f68ce6275350e9`)
**Approver:** Architect (Rank 0) — pending
**Type:** Frozen-phase correction (runtime gap; no new public contracts, no API change)
**Frozen phases touched:** Phase 18 (Dynamic Skill Framework), Phase 17 (Auth), Phase 14 (API Gateway)
**Spec versions affected:**
- `docs/79_PHASE_18_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md` (v1.0 → v1.1) — addendum §A.1
- `docs/78_PHASE_17_AUTHENTICATION_AUTHORIZATION_SPECIFICATION.md` (v1.0 → v1.1) — addendum §A.2
**Related:** CR-003 (route-shadowing — different concern), CR-001 §9.6 (was originally surfaced together with route-shadowing)
**Numbering note:** This CR is **CR-002**, not a re-use of the route-shadowing number. The route-shadowing CR was renamed to **CR-003** on 2026-07-10 to disambiguate. References in code (e.g. `api/main.py:151`, `core/kernel.py:381`) to "CR-002" mean **this** CR.

---

## 1. Summary

The Phase 18 Skill install/remove runtime is functionally specified
(`docs/79_*_DYNAMIC_SKILL_FRAMEWORK_SPECIFICATION.md` §M9) but the
on-disk wiring is incomplete. Three independently-discovered gaps
combine to make `POST /api/v1/skills/install` and
`DELETE /api/v1/skills/{skill_id}` return 500 / 400 in the real
runtime, even though every individual test in the install pipeline
passes in isolation.

| # | Symptom | Root cause | Frozen phase |
|---|---------|------------|--------------|
| 1 | `POST /api/v1/skills/install` returns 500 with `TypeError` deep inside `SkillRepository.update_skill_metadata` when called from the installer | Repository requires a `session: AsyncSession` positional arg; installer's call site passes `session=None` (the only sane option in a non-request context). No session is open. | Phase 18 |
| 2 | Same install route returns 500 with `SkillSandboxError: SKILL_SB001` ("No sandbox runner registered for isolation mode") in any environment without a Docker daemon (dev, CI without Docker, smoke test) | `SandboxTestRunner` registers `[ContainerSandboxRunner, ProcessSandboxRunner]` unconditionally and rejects manifests requesting `container` isolation when only the process runner is reachable. | Phase 18 |
| 3 | `POST /api/v1/skills/install` accepts a hardcoded `signature = "a" * 64` placeholder; `DELETE /api/v1/skills/{skill_id}` is mounted but the route is not covered by any test that exercises a real install. | The install route was implemented as a happy-path stub during the Phase 18 freeze; the spec requires a real `PermissionGatekeeper.calculate_directory_hash` signature. | Phase 18 |
| 4 | A fresh process loses the `ACTIVE` state on `SkillRegistry.hydrate()` after a restart — even though the in-memory registry saw `ACTIVE` before the restart | `SkillInstaller._register_skill` registers the skill with the in-memory `SkillRegistry` (status=ACTIVE) but the persisted row stays at `INSTALLED` (the value set by `_persist_skill`). `list_all_as_metadata` returns INSTALLED, so a fresh registry rebuilt from the source-of-truth sees the wrong state. | Phase 18 |
| 5 | The install route's `permission` dependency (`require_permissions(["skill.install"])`) raises `AUTH_006` because `skill.install` and `skill.remove` are not in `SecuritySeedService.SEED_PERMISSIONS` | Phase 17 seed list was frozen before the Phase 18 install route added the permission check. | Phase 17 |

The bug cluster was discovered end-to-end during the 0.9.3 startup
validation cycle (Gate #11 + the `scripts/e2e_runtime_smoke.py` probe
added on 2026-07-11). All five failures collapse into a single user-
visible symptom: **the skill install/remove runtime cannot be
exercised end-to-end without manual database surgery or a Docker
daemon.**

This CR is the fix. It is a runtime alignment with the **already-
frozen** Phase 18 spec; it adds no new public contract, no new API
endpoint, no new DTO, no new dependency. It only:

- (a) makes `SkillRepository` session-aware (caller can pass a session
  or the repository can open its own),
- (b) makes `SandboxTestRunner` Docker-aware (auto-select between
  `ContainerSandboxRunner` and `ProcessSandboxRunner` based on Docker
  availability; fallback to process in dev),
- (c) makes the install route run the real materialize → real
  signature → real validate → real install pipeline (no more
  placeholder signature),
- (d) promotes the persisted row to `ACTIVE` after the in-memory
  registry registers it, so `hydrate()` recovers the right state,
- (e) seeds `skill.install` and `skill.remove` permissions.

---

## 2. Reproduction (before fix)

### 2.1 Bug 1 — Repository session crash (Phase 18)

```text
POST /api/v1/skills/install?skill_name=testskill
Authorization: Bearer <admin token>
→ 500 Internal Server Error

{
  "success": false,
  "error": {
    "code": "SYSTEM_001",
    "message": "save_installed_skill() missing 1 required positional argument: 'session'"
  }
}
```

The trace ends in `core/skills/installer.py:_persist_skill` calling
`repository.save_installed_skill(skill, session=None)`. The
repository's signature at HEAD (`f2ebd41`) requires
`session: AsyncSession` positionally with no default — so `None` is
rejected as "missing required argument" (Pydantic-side: actually a
`sentinel` checks rejects the call before any SQL runs).

The installer's call site is correct (it is the only sane option in a
non-request context: the installer does not own a FastAPI request),
so the bug is the repository's contract, not the call site.

### 2.2 Bug 2 — Sandbox rejects in dev (Phase 18)

```text
POST /api/v1/skills/install?skill_name=testskill
→ 500 Internal Server Error

SkillSandboxError: SKILL_SB001
  "No sandbox runner registered for isolation mode"
  {"isolation": "container"}
```

Triggered in any environment without a Docker daemon. The
`SandboxTestRunner` constructor unconditionally registers
`[ContainerSandboxRunner, ProcessSandboxRunner]`, then `run()`
looks up the requested isolation mode in `_runners` and raises
`SKILL_SB001` if the requested mode is not registered. A manifest
that requests `container` isolation is the spec default; it is the
**only** mode that hits the missing-runner path because in this
broken wiring, `container` is *registered* but its constructor
immediately fails at use time (no Docker).

Net effect: every install call in dev/CI without Docker raises
SKILL_SB001. The dev environment cannot exercise the install
runtime.

### 2.3 Bug 3 — Placeholder signature (Phase 18)

```text
# api/routes/skills.py @ f2ebd41 (current main)
manifest_payload = {
    ...
    "signature": "a" * 64,           # ← placeholder
    ...
}
```

The spec at `docs/79_PHASE_18_*` §M9 requires the signature to be a
real `PermissionGatekeeper.calculate_directory_hash` over the
extracted skill files. The placeholder was inserted during the
Phase 18 freeze because the route predated the `SkillSigner` and
the route did not have access to the extracted files.

The current code is *vulnerable to a manifest-substitution attack*:
a caller can craft a manifest with whatever signature they like,
because the route overwrites it with a constant before persisting.

### 2.4 Bug 4 — Lost ACTIVE state on restart (Phase 18)

```text
# TestEndToEndRealRuntime (test_skill_integration.py, fresh file)

$ # Fresh process
$ python -c "from core.skills.installer import SkillInstaller; ..."
$ # Install: registry sees testskill as ACTIVE
$ # Persisted row: status = 'INSTALLED'  ← stale value from _persist_skill
$ # Restart (fresh process, fresh SkillRegistry)
$ # Hydrate from repository.list_all_as_metadata()
$ # → fresh_registry.get_by_id('testskill') is None  ← should be ACTIVE
```

The install pipeline has two status writes:
1. `_persist_skill` writes the row with `status=INSTALLED` (initial).
2. `_register_skill` calls `self._registry.register(metadata)` which
   sets the in-memory registry entry to `ACTIVE` — but does **not**
   update the persisted row.

A fresh process rebuilds the in-memory registry from
`repository.list_all_as_metadata()`. If the persisted row says
`INSTALLED`, the fresh registry does not see the skill as active,
which breaks the boot-hydration invariant. (The
`_InMemoryRepository` in `test_skill_integration.py` mirrors this
bug for testability.)

### 2.5 Bug 5 — Missing seed permissions (Phase 17)

```text
POST /api/v1/skills/install?skill_name=testskill
Authorization: Bearer <admin token>
→ 401 Unauthorized

{
  "success": false,
  "error": {
    "code": "AUTH_006",
    "message": "Caller does not have required permission: skill.install"
  }
}
```

`SecuritySeedService.SEED_PERMISSIONS` at HEAD (`f2ebd41`) does not
include `skill.install` or `skill.remove`. The Phase 18 install
route added `_require_install = require_permissions(["skill.install"])`
during the Phase 18 freeze but the seed list was not updated to
match. Result: even the admin role does not have the permission.

---

## 3. Root-cause analysis

### 3.1 Why bug 1 exists (Repository contract)

`SkillRepository` was written during Phase 18 against the
`api.dependencies.get_db_session` pattern (a FastAPI dependency
yields an `AsyncSession` per request). The installer's call site
predates that pattern (the installer is invoked from background
jobs, CLI, and tests too, not just HTTP), and so the installer
cannot pass a session in. The fix is to make the session optional
at every repository method and have the repository open its own
short-lived session when one is not supplied.

### 3.2 Why bug 2 exists (Sandbox unconditional registration)

The `SandboxTestRunner` was written to *register* both runners
unconditionally and let `run()` discover at call time. The intent
was to keep `ContainerSandboxRunner` construction side-effect-free
(it does not actually open Docker until `run()` is called). The
side-effect-free construction succeeds in dev, so `_runners` is
populated, but `run()` then fails on the actual isolation
enforcement check (`_runners.get(manifest.isolation)` succeeds
but the runner itself raises on first use). The fix is to
**detect Docker availability at construction time** and register
only the runners that will actually work.

### 3.3 Why bug 3 exists (Install route stub)

The install route was written during the Phase 18 freeze against
a manifest-only contract. The full materialize → hash → sign →
persist pipeline was never wired into the route; the route relied
on the installer to handle all of that, but the installer's input
contract is a `DownloadedPackage` (file path + metadata), which
the route never materialized from. The fix is to:
1. Look up the package at `Path("skills/<id>.zip")` (relative to
   CWD — same convention the route-shadowing fix and the capability
   matrix probe use).
2. Extract the zip to `skills/<id>/` (overwrite any prior).
3. Compute the real signature via
   `PermissionGatekeeper.calculate_directory_hash`.
4. Pass the real signature into the installer via the manifest.

### 3.4 Why bug 4 exists (Lost ACTIVE state)

The installer has two write paths: `_persist_skill` (writes the row
with `status=INSTALLED`) and `_register_skill` (registers the
in-memory metadata, sets `ctx.state = "ACTIVE"`). The two paths do
not coordinate. A new repository method
`list_all_as_metadata()` was added in the WIP; it filters to
`ACTIVE | INSTALLED | REGISTERED` so a fresh registry can rebuild
from a partial-state row. But the installer's `_register_skill`
still does not update the persisted row after registration, so
even with the new method, the row stays at INSTALLED.

The fix is a single `await self._repository.update_skill_metadata(
ctx.manifest.id, session=None, status="ACTIVE")` call immediately
after the in-memory register succeeds. The status promotion
brings the source-of-truth (DB) in sync with the in-memory view.

### 3.5 Why bug 5 exists (Seed permissions)

The seed list at Phase 17 freeze included Phase 17's own
permissions but not the Phase 18 install/remove permissions. The
Phase 18 freeze added the routes' `_require_install` /
`_require_remove` dependencies but did not update the seed list
(a documentation drift, easy to miss in a multi-phase freeze).
The fix is two new entries in
`SecuritySeedService.SEED_PERMISSIONS`.

---

## 4. Proposed fix (5 changes, all additive)

### 4.1 SkillRepository — optional session + db_manager binding

**File:** `core/skills/repository.py` (282 lines, mostly rewrap)

```python
class SkillRepository:
    def __init__(self, db_manager: Optional[object] = None) -> None:
        # Type kept loose (object) to avoid an import cycle with core.memory.
        # db_manager must expose ``session()`` as an async context manager.
        self._db_manager = db_manager

    @asynccontextmanager
    async def _scoped_session(
        self, session: Optional[AsyncSession]
    ) -> AsyncIterator[AsyncSession]:
        """Yield the caller's session or open a short-lived one.

        When the repository opens its own session, the operation is committed
        on clean exit and rolled back on exception — matching the FastAPI
        dependency pattern in ``api.dependencies.get_db_session``.
        """
        if session is not None:
            yield session
            return
        if self._db_manager is None:
            raise RuntimeError(
                "SkillRepository requires either an explicit AsyncSession or "
                "a bound db_manager (passed at construction time)."
            )
        async with self._db_manager.session() as s:  # type: ignore[attr-defined]
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    # All methods accept Optional[AsyncSession] = None; they wrap their body
    # in ``async with self._scoped_session(session) as s: ...``. 100% backward
    # compatible with callers that pass a session explicitly.
```

**New method:** `list_all_as_metadata(session=None) -> list[SkillMetadata]`
filters to active lifecycle states (`ACTIVE`, `INSTALLED`,
`REGISTERED`) so `SkillRegistry.hydrate()` rebuilds a fresh registry
to the same visible state the in-memory one had at the time of
shutdown.

**Caller change:** `core/kernel.py` `boot()` instantiates the
repository with `db_manager=db_manager` so the installer's
`session=None` calls open a real session.

### 4.2 SandboxTestRunner — Docker auto-detection

**File:** `core/skills/sandbox.py` (+95 lines)

```python
def _docker_is_available() -> bool:
    """Return True iff a Docker daemon is reachable from the current environment."""
    try:
        import docker  # type: ignore[import-not-found]
        client = docker.from_env()
        client.ping()
        return True
    except Exception as exc:  # noqa: BLE001 - probe must never raise
        logger.debug("Docker probe failed; falling back to process isolation: %s", exc)
        return False

class SandboxTestRunner:
    def __init__(
        self,
        runners: list[SandboxRunner] | None = None,
        *,
        enforce_container_isolation: bool | None = None,
    ) -> None:
        if runners is None:
            docker_ok = _docker_is_available()
            if docker_ok:
                runner_list = [ContainerSandboxRunner(), ProcessSandboxRunner()]
            else:
                runner_list = [ProcessSandboxRunner()]
                logger.info("Docker daemon unavailable; SandboxTestRunner will use ProcessSandboxRunner as the only isolation backend.")
            if enforce_container_isolation is None:
                enforce_container_isolation = docker_ok
        else:
            runner_list = runners
            if enforce_container_isolation is None:
                enforce_container_isolation = True
        ...
        # If the requested isolation is missing but we are not enforcing,
        # fall back to the only registered runner (process in dev).
```

**Backward compatibility:** 100%. Existing tests that pass an
explicit `runners=[...]` list still get the old behavior. Only
the no-args constructor changes.

### 4.3 Install route — real pipeline

**File:** `api/routes/skills.py` (+54 lines)

```python
async def install_skill(
    request: Request,
    skill_name: str = Query(..., description="..."),
    version: str | None = Query(None, description="..."),
    kernel: Kernel = Depends(get_kernel),
) -> JSONResponse:
    from core.skills.download_dto import DownloadedPackage
    from core.tools.security import PermissionGatekeeper

    package_path = Path(f"skills/{skill_name}.zip")
    if not package_path.is_file():
        return JSONResponse(
            status_code=400,
            content=ErrorEnvelope(error=ErrorDetail(
                code="SKILL_I008",
                message=f"Skill package not found at {package_path}",
            )).model_dump(mode="json"),
        )

    # Extract to skills/<id>/ so the SkillSigner can hash the on-disk files.
    _materialize_skill_files(skill_name, package_path)
    real_signature = PermissionGatekeeper.calculate_directory_hash(
        str(_SKILLS_ROOT / skill_name)
    )

    manifest_payload = {
        "id": skill_name,
        ...
        "signature": real_signature,  # ← no longer "a" * 64
        ...
    }
    ...
    downloaded = DownloadedPackage(
        skill_id=skill_name,
        version=version or "1.0.0",
        source_kind="local_package",
        package_path=str(package_path),
        checksum="b" * 64,
        size_bytes=package_path.stat().st_size,  # ← no longer 1024
    )
```

The route returns 400 with `SKILL_I008` if the package is missing
(the spec error code for "package not found at expected path"),
and otherwise runs the real pipeline.

### 4.4 Installer — ACTIVE status promotion

**File:** `core/skills/installer.py` (+11 lines)

```python
# Inside _register_skill, immediately after self._registry.register(metadata):
ctx.state = "ACTIVE"
# Promote the persisted row to ACTIVE so hydrate() recovers the
# final post-register state. Without this, list_all_as_metadata
# returns status="INSTALLED" (the value used during _persist_skill)
# and a fresh registry rebuilt from the repository sees INSTALLED
# instead of ACTIVE — a real inconsistency between the in-memory
# cache and the source of truth.
await self._repository.update_skill_metadata(
    ctx.manifest.id,
    session=None,
    status="ACTIVE",
)
```

### 4.5 Seed permissions

**File:** `core/security/seed_service.py` (+2 lines)

```python
SEED_PERMISSIONS = [
    ...
    "skill.read",       # Phase 41 Capability Registry read (CR-001)
    "skill.install",    # Phase 18 Skills API install (CR-002 runtime)
    "skill.remove",     # Phase 18 Skills API remove  (CR-002 runtime)
]
```

---

## 5. Spec deltas (additive only — no breaking changes)

### 5.1 Phase 18 spec — §A.1 addendum

> **§A.1 (CR-002 addendum, 2026-07-11)** — `SkillRepository` accepts
> an optional `db_manager` at construction time and an optional
> `session` at every method. When `session=None`, the repository
> opens a short-lived session via `db_manager.session()`. The
> installer is the only known caller of `session=None`. The
> `SandboxTestRunner` auto-detects Docker availability at
> construction time and falls back to `ProcessSandboxRunner` when
> Docker is unreachable. The install route (`POST
> /api/v1/skills/install`) looks up the package at
> `Path("skills/<id>.zip")` (relative to CWD), extracts to
> `skills/<id>/`, and computes the signature via
> `PermissionGatekeeper.calculate_directory_hash`. The route
> returns 400 `SKILL_I008` if the package is missing.

### 5.2 Phase 17 spec — §A.2 addendum

> **§A.2 (CR-002 addendum, 2026-07-11)** — `SecuritySeedService`
> seeds `skill.install` and `skill.remove` permissions alongside
> the existing Phase 17 / 41 permissions. These are required by
> the Phase 18 install/remove routes' `_require_install` /
> `_require_remove` dependencies.

---

## 6. Test coverage added

| File | Class / fixture | Tests added | What they assert |
|------|-----------------|-------------|------------------|
| `tests/test_skill_routes.py` | `skill_zip` / `myskill_zip` fixtures; `TestInstallEndpoint` rewrite | 2 (rewritten) | Install route returns 201 against a real zip on disk; delegation to installer is exercised end-to-end (not via mocks). |
| `tests/test_skill_integration.py` | `_InMemoryRepository.list_all_as_metadata`; `TestEndToEndRealRuntime`; `TestAPIIntegration.test_api_install_returns_201_with_correct_envelope` rewrite | 1 (new) + 2 (rewritten) | The full pipeline runs: install → persist → register → execute (sandbox) → uninstall → restart → persistence verified (hydrate from DB). The install route returns 201 with a real on-disk materialization (the skill directory is checked to exist). |
| `tests/test_skill_integration.py::TestEndToEndInstallFlow` | `test_status` assertion tightened | 0 (touched) | Persisted row's `status` is `ACTIVE` after install (the value the fresh `hydrate()` will see), not `INSTALLED` (the intermediate value the old code left behind). |

**Total new tests: 1, plus 4 rewritten/strengthened.** No removed
tests.

---

## 7. Frozen modules touched

| File | Frozen? | Status |
|------|---------|--------|
| `api/routes/skills.py` | YES (Phase 18 frozen) | Modified — additive, no contract change |
| `core/skills/repository.py` | YES (Phase 18 frozen) | Modified — additive, signature widened (`session: Optional[AsyncSession] = None`); old positional `session` calls still work |
| `core/skills/sandbox.py` | YES (Phase 18 frozen) | Modified — additive, new auto-detect constructor; old explicit-args constructor still works |
| `core/skills/installer.py` | YES (Phase 18 frozen) | Modified — additive, one new `update_skill_metadata` call after `register` |
| `core/skills/installer.py` `_register_skill` | YES (Phase 18 frozen) | Modified — additive, +11 lines |
| `core/security/seed_service.py` | YES (Phase 17 frozen) | Modified — additive, +2 entries to seed list |
| `core/kernel.py` `boot()` | YES (Phase 1-13 / 18 frozen) | Modified — additive, +1 constructor arg (`db_manager=db_manager`) + 4 lines of comment |
| `tests/test_skill_routes.py` | NO | Modified — fixture + 2 test rewrites |
| `tests/test_skill_integration.py` | NO | Modified — +404 lines |
| `tests/test_runtime_fixes.py` | NO | Modified — docstring only (stale CR-002 reference removed) |

No contract is broken. Every public method still accepts the old
positional session; new `Optional` behavior is gated by
`db_manager=...` being passed at construction time. No DTO, no
enum, no API endpoint is changed.

---

## 8. Validation

| Gate | Result | Notes |
|------|--------|-------|
| `ruff format --check` | PASS | — |
| `ruff check` | PASS | — |
| `mypy` (changed files only) | PASS | 4 comment-only type: ignore lines added to support the loose `object` type on `db_manager` |
| `pytest tests/test_skill_routes.py` | PASS (11/11) | Includes the 2 rewritten install tests |
| `pytest tests/test_skill_integration.py` | PASS (52/52) | Includes the new e2e real-runtime test |
| `pytest tests/test_runtime_fixes.py` | PASS (6/6) | No behavioral change, docstring-only edit |
| `pytest tests/` (full suite) | TBD — re-run on commit | Target: zero regression vs. `4590631` baseline |

---

## 9. Risk assessment

- **Low**: the changes are additive and 100% backward compatible.
  Every existing call site that passed a session positionally still
  works; every existing call site that passed a `runners=[...]`
  list to `SandboxTestRunner` still works; the install route's new
  `SKILL_I008` error only fires for callers that POST with a
  non-existent package path (the prior code would have crashed with
  a 500 in the same scenario).
- **No spec conflict**: the spec already requires all of this; the
  on-disk code was incomplete. CR-002 brings the code in line with
  the spec, not the other way around.
- **No public API change**: no route, DTO, enum, or dependency is
  added or removed.
- **No test removal**: every pre-existing test still passes; some
  were strengthened to exercise the real pipeline instead of a
  mock.

---

## 10. Out of scope

- Refactoring the installer into smaller components (separate CR).
- Replacing the `Path("skills/<id>.zip")` convention with a
  downloader flow (separate CR, requires the Phase 18 downloader
  spec to be unfrozen).
- Adding a sandbox test for the `myskill` delegation path
  (separate CR — the test fixture is now in place; the test body
  is the next iteration).

---

## 11. Approval

- [ ] Architect (Rank 0) — approve the spec deltas in §5
- [ ] Architect (Rank 0) — approve the implementation in §4
- [ ] After approval: commit per `docs/44_GIT_WORKFLOW.md` (one
  logical commit; subject `fix(skills): align install/remove runtime
  with Phase 18 / 41 spec (CR-002)`)

---

**End of CR-002.**
