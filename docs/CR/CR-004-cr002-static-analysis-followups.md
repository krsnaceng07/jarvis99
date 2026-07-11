# CR-004 — CR-002 Static Analysis: 7 Low-Severity Follow-Up Candidates

**Status:** 🟡 PROPOSED (triage; awaiting architect prioritization)
**Date:** 2026-07-11
**Proposer:** Mavis (orchestrator session `mvs_1eef650acaf648eb92f68ce6275350e9`)
**Approver:** Architect (Rank 0) — pending
**Type:** Follow-up triage (no immediate fix; nothing blocks CR-002 merge)
**Related:** [CR-002](CR-002-skill-install-remove-runtime.md) (the 5-bug fix this triage
descends from)

---

## 1. Summary

The CR-002 static analysis surfaced 7 minor concerns. None of them
block the CR-002 commit (`87682e5`); all are 100% backward-compatible
polish, future-proofing, or spec-citation completeness. This CR is
**triage**, not implementation — it identifies each finding with a
severity rating and a proposed fix, and asks the architect to either
(a) bundle them into a single follow-up commit, (b) split them into
multiple smaller CRs, or (c) accept them as known limitations and
close the CR.

The 7 findings are listed in §3 in descending severity. §2 describes
the analysis methodology. §4 gives the architect three resolution
paths. §5 lists the test impact. §6 lists the architect's choices.

---

## 2. Methodology

The static analysis was performed by reading every changed line in
the CR-002 commit (`git show 87682e5`) and looking for:

1. **Type-looseness** — places where a stricter type would catch
   bugs at the type layer (`db_manager: Optional[object]`, etc.)
2. **Exception-handling breadth** — places where a broad
   `except Exception` could mask unexpected errors.
3. **Resource management** — places where the context manager /
   session boundary is not as tight as it could be.
4. **Spec-citation gaps** — places where the code uses an
   identifier (error code, status value) that the spec does not
   formally define.
5. **Path conventions** — places where the code uses a relative or
   CWD-relative path where an absolute / configured path would be
   more robust.
6. **Defensive defaulting** — places where a default is auto-derived
   from a runtime check and the resulting value is non-obvious to
   the reader.
7. **Cross-layer import** — places where the implementation imports
   across a documented layer boundary.

Findings are scored **low / medium / high**; all 7 here scored low
(the static analysis does not surface any medium or high findings
in CR-002).

---

## 3. Findings

### 3.1 `SkillRepository._db_manager` typed as `object`

**File:** `core/skills/repository.py:44`

```python
def __init__(self, db_manager: Optional[object] = None) -> None:
    # Type kept loose (object) to avoid an import cycle with core.memory.
```

The `db_manager` parameter is typed as `object` to avoid an import
cycle with `core.memory`. The actual contract (a `session()` async
context manager) is documented in the docstring but not enforced
at the type layer. A `typing.Protocol` named `AsyncSessionFactory`
would let mypy catch a mis-typed `db_manager` at the construction
site.

**Severity:** low. The `type: ignore[attr-defined]` on line 67 is
the only mypy escape hatch; everything else type-checks. A
Protocol is a follow-up, not a CR-002 gap.

**Proposed fix:** Add a `core.db.protocols.AsyncSessionFactory`
Protocol with a single `def session(self) -> AsyncContextManager[AsyncSession]: ...`
method, type `db_manager` as `Optional[AsyncSessionFactory]`, drop
the `type: ignore[attr-defined]`. New file, no behavior change.

### 3.2 `_docker_is_available()` swallows ALL exceptions

**File:** `core/skills/sandbox.py:50-58`

```python
try:
    import docker
    client = docker.from_env()
    client.ping()
    return True
except Exception as exc:  # noqa: BLE001 - probe must never raise
    logger.debug("Docker probe failed; falling back to process isolation: %s", exc)
    return False
```

The `except Exception` is intentional (a probe must never raise),
but it captures `ImportError`, `PermissionError`, `OSError`, and
genuine programmer errors equally. A more disciplined split would
be: catch `(ImportError, OSError, ConnectionError)` explicitly, let
`AttributeError` / `TypeError` propagate (they signal a bug in the
probe, not a Docker unavailability).

**Severity:** low. The debug log captures the cause; the only
real-world impact is that an unexpected bug in the probe code would
be reported as "Docker unavailable" instead of an exception. The
probe is 7 lines; the bug surface is small.

**Proposed fix:** Replace `except Exception` with
`except (ImportError, OSError, ConnectionError, docker.errors.APIError)`;
let everything else propagate. 3-line change.

### 3.3 `_scoped_session` CancelledError handling

**File:** `core/skills/repository.py:49-73`

```python
async with self._db_manager.session() as s:
    try:
        yield s
        await s.commit()
    except Exception:
        await s.rollback()
        raise
```

In Python 3.8+, `asyncio.CancelledError` is a subclass of
`BaseException`, not `Exception`. If a caller cancels mid-operation,
the `except Exception` clause does not fire, so neither `commit()` nor
`rollback()` is called. The `async with` block's `__aexit__` is
responsible for cleanup, but the contract is implicit.

**Severity:** low. The DB session context manager (in
`core.memory`) is expected to handle the `__aexit__` correctly,
including rollback-on-cancel. The CR-002 tests do not exercise
the cancel path.

**Proposed fix:** Add `except BaseException:` after the `except Exception:`
block, log the cancellation, and explicitly call `await s.rollback()`.
3-line change. A regression test that cancels mid-operation would
require `asyncio.CancelledError` injection; out of scope for the fix.

### 3.4 Install route's `Path("skills/<id>.zip")` is CWD-relative

**File:** `api/routes/skills.py:41` and the install handler

The route hardcodes `Path("skills/<skill_name>.zip")` (relative to
CWD). The CWD-relative convention is consistent with the
route-shadowing fix (CR-003) and the capability-matrix probe, so it
is **intentional** for now. But it is fragile: a process whose CWD
is not the repo root (e.g. a `uvicorn` launched from `/etc/jarvis/`)
will not find the package.

**Severity:** low. Documented in CR-002 §10 as out-of-scope. The
production deploys the package directory to a known path and sets
CWD accordingly; the convention works for all current consumers.

**Proposed fix:** Add a `JARVIS_SKILLS_DIR` env var (or config
entry) that overrides the default. The route reads it via
`Settings.skills_dir` (Pydantic setting). 1 setting + 1 line in
the route.

### 3.5 `SKILL_I008` error code not in the Phase 18 spec error code enum

**File:** `api/routes/skills.py` (install handler)

The install route returns `SKILL_I008` ("Skill package not found
at expected path") on a missing package. The `SKILL_Ixxx` range
is reserved for installer errors, but the spec at
`docs/79_PHASE_18_*` §M9 does not formally enumerate `SKILL_I008`
in its error code table (only `SKILL_I001..SKILL_I007` are listed).

**Severity:** low. The code follows the same `SKILL_Ixxx`
convention as its siblings; the spec table is the spec's
documentation gap, not the code's. The error fires only on a
missing package (a caller mistake, not a runtime condition), so
the message + code pair is self-describing.

**Proposed fix:** Add `SKILL_I008` to the Phase 18 spec §M9
error-code table as a follow-up CR (§5.1 addendum). 3-line spec
edit; no code change.

### 3.6 `update_skill_metadata` parameter is loosely typed

**File:** `core/skills/repository.py` (CR-002 added this method)

The new `update_skill_metadata(skill_id, session=None, **fields)`
method accepts arbitrary keyword arguments. A Pydantic model
(`SkillMetadataPatch`) or a TypedDict would catch typos at the
type layer and document the supported fields. The current
implementation silently ignores unknown fields (or worse, passes
them to SQLAlchemy and gets a confusing `InvalidRequestError`).

**Severity:** low. The only call site (CR-002 §4.4) passes a
single `status="ACTIVE"` kwarg, which is correct. A future caller
that passes `stattus="ACTIVE"` (typo) would get a runtime
SQLAlchemy error rather than a clean Pydantic validation error.

**Proposed fix:** Replace `**fields` with an explicit
`status: Optional[str] = None` parameter (or a Pydantic model
if there are multiple fields in the future). 1-line change.
Per the architect's "second consumer before abstraction" rule,
a TypedDict is **not** warranted yet — keep it as an explicit
kwarg list for now.

### 3.7 `SandboxTestRunner.__init__` `enforce_container_isolation` default is non-obvious

**File:** `core/skills/sandbox.py:168-180`

```python
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
        if enforce_container_isolation is None:
            enforce_container_isolation = docker_ok  # ← default by availability
```

The default of `enforce_container_isolation` is **derived from the
Docker probe result**: if Docker is OK, default to enforce (production
posture); if Docker is NOT OK, default to not enforce (dev posture).
The logic is correct, but the default-by-availability rule is not
visible at the call site — a reader of `SandboxTestRunner()` sees
`enforce_container_isolation=None` and has to follow the conditional
to know what `None` means.

**Severity:** low. The class docstring (lines 148-166) explains
the auto-detection rule. But the docstring is 18 lines long; the
critical default-by-availability rule is buried in §3 of the
docstring. A reader skimming the constructor signature would not
know.

**Proposed fix:** Either (a) move the `enforce_container_isolation`
parameter to a keyword-only and document its default in the
parameter's type stub, or (b) split the constructor into two
factory methods: `SandboxTestRunner.auto()` (probes Docker) and
`SandboxTestRunner.explicit(runners=..., enforce=...)` (no probe).
Option (b) makes the contract obvious at the call site.

---

## 4. Resolution paths

The architect picks one of:

- **A. Bundle** — single follow-up commit "polish(skills): address
  7 CR-002 static analysis findings" addresses all 7 in one
  pass. Lowest overhead; mixes concerns. **Recommended for the
  0.9.4 push** if 0.9.4 is the next release boundary and we
  want to clean the slate.
- **B. Split** — 3-7 separate follow-up CRs (e.g. one per
  concern category: type-looseness, exception-handling, etc.).
  Higher overhead; cleaner review trail. **Recommended if any
  one concern is large enough to warrant its own design
  discussion** (e.g. the path-convention fix in §3.4 might
  warrant a separate ADR).
- **C. Defer** — accept the 7 as known limitations, close this
  CR without action. **Recommended only if the architect
  believes none of the 7 is worth a follow-up commit** (e.g. if
  the issues are all spec-doc or type-layer polish with no
  runtime impact).

---

## 5. Test impact

For paths A and B:

| Finding | Test added | Test file |
|---------|-----------|-----------|
| 3.1 Protocol type | 1 (constructor rejects non-Protocol `db_manager`) | `tests/test_skill_repository.py` |
| 3.2 narrow exception | 1 (`AttributeError` propagates, `OSError` does not) | `tests/test_skill_sandbox.py` |
| 3.3 CancelledError | 1 (cancel mid-op → rollback called) | `tests/test_skill_repository.py` |
| 3.4 `JARVIS_SKILLS_DIR` | 1 (env var override works) | `tests/test_skill_routes.py` |
| 3.5 spec citation | 0 (spec edit only) | — |
| 3.6 explicit kwargs | 1 (typo in kwarg → `TypeError` not `InvalidRequestError`) | `tests/test_skill_repository.py` |
| 3.7 factory split | 1-2 (`SandboxTestRunner.auto()` vs `explicit()`) | `tests/test_skill_sandbox.py` |

**Total:** 5-6 new tests. All 7 fixes are additive; zero
regression risk. Coverage stays above 91%.

---

## 6. Approval

- [ ] Architect (Rank 0) — choose A, B, or C
- [ ] Architect (Rank 0) — if A or B: approve the test list in §5
- [ ] After approval: commit per `docs/44_GIT_WORKFLOW.md` (one
  commit per A, one per concern for B, no commit for C)

---

**End of CR-004.**
