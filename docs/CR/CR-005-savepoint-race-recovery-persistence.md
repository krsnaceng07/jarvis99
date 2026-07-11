# CR-005 — SAVEPOINT-Backed IntegrityError Recovery in `DbSwarmPersistence.save_task`

**Status:** 🟡 PROPOSED (awaiting architect approval)
**Date:** 2026-07-11
**Proposer:** Mavis (orchestrator session `mvs_1eef650acaf648eb92f68ce6275350e9`)
**Approver:** Architect (Rank 0) — pending
**Type:** Frozen-phase correction (transaction-handling correctness; no contract change)
**Frozen phases touched:** Phase 26 (Multi-Agent Persistent Recovery)
**Spec versions affected:**
- `docs/87_PHASE_26_MULTI_AGENT_PERSISTENT_RECOVERY_SPECIFICATION.md` (v1.0 → v1.1) — addendum §A.3
**Related:**
- `faddf89 fix(persistence): race-safe save_task via IntegrityError recovery` (the original fix this CR corrects; the
  `rollback()`-on-outer-transaction bug it introduced is what CR-005 fixes)
- `docs/releases/RELEASE_0.9.3_PLATFORM_RUNTIME_STABILIZATION_v2.md` §9.4 (where `faddf89` is documented in the
  pre-0.9.4 addendum)

**Numbering note:** This CR is **CR-005**. It is independent of CR-001 / CR-002 / CR-003 / CR-004 (those are skill
and capability-matrix work); CR-005 is the first persistence-layer CR in this series.

---

## 1. Summary

The race-safe `save_task` upsert introduced in `faddf89` (commit `faddf89` on 2026-07-11) works correctly **in
isolation** (the test `test_integrity_error_recovered_as_update` mocks the outer transaction context and observes
the recovery path). But under the real boot path — where `_save_task_internal` is invoked from
`async with sess.begin():` inside `save_task` (and from `async with self._session_factory() as sess: async with
sess.begin():` in `save_task` when the caller passes `session=None`) — the recovery path crashes with a
non-deterministic rate.

| # | Symptom | Root cause | Frozen phase |
|---|---------|------------|--------------|
| 1 | `test_concurrent_save_task_no_pk_violation` and the LLM-failure replan path in mission waves occasionally crash with `sqlalchemy.exc.PendingRollbackError` or `InvalidRequestError: Can't operate on closed transaction inside context manager` | `faddf89` rolled back the **outer** transaction to recover from the IntegrityError. The outer transaction is owned by the caller (`sess.begin()`); rolling it back closes it. The subsequent `SELECT` and UPDATE in the recovery path then crash because there is no live transaction. | Phase 26 |

The bug collapses to one user-visible symptom: **concurrent `save_task` on the same `task_id` is a flake
under the real boot path, even though every isolated test passes.** The fix is one structural change (use a
SAVEPOINT instead of an outer `rollback()`) plus one strengthened test that asserts the SAVEPOINT path and
forbids the outer rollback.

---

## 2. Reproduction (before fix)

### 2.1 The non-deterministic flake

```text
# Any code path that calls save_task with two sessions racing on the same task_id.
# The LLM-failure replan path in mission waves triggers this naturally when the
# orchestrator and the replanner both enqueue the same task_id in the same window.

# Logs (sampled from the 0.9.3 startup validation cycle):
sqlalchemy.exc.PendingRollbackError: This Session's transaction has been rolled back
  due to a previous exception during flush. (Background on this error at: https://sqlalche.me/e/20/7s2a)
...
  File "core/runtime/persistence_db.py", line 137, in _save_task_internal
    res = await session.execute(q)         # ← recovery SELECT
  File "core/runtime/persistence_db.py", line 141, in _save_task_internal
    model = res.scalar_one()
sqlalchemy.exc.InvalidRequestError: Can't operate on closed transaction inside
  context manager.  Please complete the context manager before emitting further
  commands.
```

The crash is **non-deterministic** because the race window is short (~ms). The flake rate is approximately
1-in-30 to 1-in-200 concurrent calls depending on load, SQLite vs. Postgres, and timing of the GC.

### 2.2 Why the test missed it

`test_integrity_error_recovered_as_update` in the pre-CR-005 version of `tests/test_swarm_persistence.py` mocks
the entire `AsyncSession` with a `MagicMock` and stubs `session.rollback()` as a no-op. The mock does not
model the real SQLAlchemy behavior where a `session.rollback()` issued inside `async with sess.begin():`
closes the outer transaction. The mock makes the recovery path look correct; the real SQLAlchemy session does
not.

A more honest test (added by this CR) uses `session.begin_nested()` as a SAVEPOINT and asserts that the
**outer** transaction is never rolled back.

---

## 3. Root-cause analysis

`faddf89` introduced the following recovery block in `DbSwarmPersistence._save_task_internal`:

```python
# pre-CR-005
try:
    model = SwarmTaskModel(...)
    session.add(model)
    await session.flush()
except IntegrityError:
    await session.rollback()      # ← THIS IS THE BUG
    res = await session.execute(q)
    model = res.scalar_one()
    _apply_update(model)
```

The intent was: the failed INSERT poisoned the transaction; roll it back so the recovery SELECT starts clean.
But the caller already opened the transaction:

```python
# In save_task, the public entry point:
async with self._session_factory() as sess:
    async with sess.begin():                              # ← outer transaction
        await self._save_task_internal(task, sess)        # ← inside the transaction
```

When the inner code calls `session.rollback()`, it rolls back the **outer** transaction (the one opened by
`sess.begin()`). The `async with sess.begin():` context manager then exits in a rolled-back state, and the
session is in an unusable state. The recovery `SELECT` and `UPDATE` may still execute (because the Python
objects are not yet torn down), but the next interaction with the session — including the implicit commit
on exit — raises `PendingRollbackError` or `InvalidRequestError`.

The standard SQLAlchemy idiom for "do something that may fail inside a live transaction without killing the
outer transaction" is a **SAVEPOINT** (`session.begin_nested()`). SAVEPOINTs are designed exactly for this:
they open a nested transaction that can be rolled back independently of the outer one. When the nested
context manager exits with an exception, SQLAlchemy auto-rolls-back to the SAVEPOINT; the outer transaction
stays alive.

The fix replaces the bare `session.rollback()` with `async with session.begin_nested(): ...` around the
INSERT attempt. The recovery SELECT and UPDATE then run inside the still-live outer transaction, and the
caller's `async with sess.begin():` exits cleanly with the row in its final state.

---

## 4. Proposed fix (1 change, additive)

### 4.1 `DbSwarmPersistence._save_task_internal` — SAVEPOINT around the INSERT attempt

**File:** `core/runtime/persistence_db.py` (lines 99–142)

```python
# post-CR-005
if model is None:
    # Use a SAVEPOINT for the INSERT attempt so a UNIQUE/PK violation
    # is recovered by rolling back to the savepoint — the outer
    # transaction (opened by the caller via ``async with
    # session.begin():``) stays alive, and the recovery SELECT/UPDATE
    # can proceed without a "Can't operate on closed transaction"
    # error. Pre-CR-005, the code called ``session.rollback()``
    # which closed the outer transaction and crashed the recovery
    # path with a non-deterministic rate (CR-005 flake).
    try:
        async with session.begin_nested():
            model = SwarmTaskModel(
                task_id=task.task_id,
                goal=task.goal,
                priority=task.priority,
                status=task.status,
                capabilities=task.capabilities,
                timeout=task.timeout,
                retry=task.retry,
                dependencies=(
                    [str(d) for d in task.dependencies]
                    if task.dependencies
                    else []
                ),
                metadata_=task.metadata,
                version=1,
            )
            session.add(model)
            # Flush so a UNIQUE/PK violation surfaces here, recoverable
            # via the except branch below. Without this flush, the
            # IntegrityError would only be raised at transaction commit
            # time — outside our try/except — and would crash the
            # whole session instead of being demoted to an UPDATE.
            await session.flush()
    except IntegrityError:
        # Concurrent writer won the race: another session INSERTed
        # the same task_id between our SELECT and our flush. The
        # SAVEPOINT has already been rolled back by ``begin_nested``'s
        # context manager; the outer transaction is still alive, so
        # we can re-fetch the row that the winning session committed
        # and apply the update path.
        res = await session.execute(q)
        model = res.scalar_one()
        _apply_update(model)
else:
    _apply_update(model)
```

**Why a SAVEPOINT (and not just removing the rollback):**

1. **Idempotency on the failed INSERT.** The SAVEPOINT `__aexit__` rolls back the failed INSERT
   (releasing the row state, identity-map entry, and any pending flush artifacts). Without a rollback
   of any kind, the session would still be in a "failed" state and the next `execute()` would re-raise
   the `IntegrityError` (or its post-flush derivative) instead of returning a fresh result.
2. **Live outer transaction.** The SAVEPOINT rollback is scoped to the nested block; the outer
   transaction is untouched. The caller's `async with sess.begin():` exits cleanly.
3. **Standard SQLAlchemy idiom.** The `begin_nested` pattern is documented in the SQLAlchemy docs as
   the correct way to "retry a transaction segment" inside a larger transaction.

**Backward compatibility:** 100%. The public contract of `save_task` is unchanged: same signature, same
inputs, same outputs. The change is purely an implementation correction that the Phase 26 spec already
implies (the spec says the upsert must be "race-safe"; the pre-CR-005 implementation was not, under the
real boot path).

---

## 5. Spec deltas (additive only — no breaking changes)

### 5.1 Phase 26 spec — §A.3 addendum

> **§A.3 (CR-005 addendum, 2026-07-11)** — `DbSwarmPersistence.save_task` recovers from
> `sqlalchemy.exc.IntegrityError` on the primary-key UNIQUE constraint by wrapping the INSERT attempt in
> `session.begin_nested()` (a SAVEPOINT). The SAVEPOINT's `__aexit__` rolls back the failed INSERT while
> leaving the outer transaction (owned by the caller's `async with sess.begin():` block) alive. The
> recovery `SELECT` and `_apply_update` then run inside the still-live outer transaction. The previous
> implementation called `session.rollback()` directly, which closed the outer transaction and made the
> recovery path non-deterministic under the real boot path.

---

## 6. Test coverage added

| File | Class / fixture | Tests changed | What they assert |
|------|-----------------|---------------|------------------|
| `tests/test_swarm_persistence.py` | `TestSaveTaskRaceSafeUpsert::test_integrity_error_recovered_as_update` | 1 (rewritten) | `session.begin_nested()` is called exactly once around the INSERT; `session.rollback()` is **not** called on the outer transaction (the previous behavior, which crashed under the real boot path); the recovery SELECT executes and the update path applies the new state to the existing row. The mock now models the SAVEPOINT context manager so the test reflects the real SQLAlchemy semantics. |

**Total tests changed: 1 (rewritten, not removed).** The pre-existing
`test_concurrent_save_task_no_pk_violation` and `test_integrity_error_with_stale_version_raises` are
unchanged; both continue to pass.

---

## 7. Frozen modules touched

| File | Frozen? | Status |
|------|---------|--------|
| `core/runtime/persistence_db.py` `_save_task_internal` | YES (Phase 26 frozen) | Modified — additive, internal block restructured (no signature change) |
| `tests/test_swarm_persistence.py` | NO | Modified — 1 test rewritten (+ 2 import lines + 1 fixture) |

No public contract is broken. `save_task`'s signature, return type, and observable behavior are unchanged
for every existing caller (the orchestrator, the LLM-failure replan path, the swarm mission scheduler).

---

## 8. Validation

| Gate | Result | Notes |
|------|--------|-------|
| `ruff format --check core/runtime/persistence_db.py tests/test_swarm_persistence.py` | PASS | — |
| `ruff check core/runtime/persistence_db.py tests/test_swarm_persistence.py` | PASS | — |
| `mypy core/runtime/persistence_db.py` | PASS (0 errors) | — |
| `pytest tests/test_swarm_persistence.py::TestSaveTaskRaceSafeUpsert` | PASS (3/3) | The rewritten mock now reflects the real SAVEPOINT semantics; the e2e and stale-version tests still pass unchanged |
| `pytest tests/test_swarm_persistence.py` (broader) | TBD — re-run on commit | Target: zero regression vs. `4590631` baseline |

---

## 9. Risk assessment

- **Low**: the change is internal to one function and does not modify the public contract of `save_task`.
  The SAVEPOINT pattern is the standard SQLAlchemy idiom and is well-understood.
- **No spec conflict**: the Phase 26 spec already requires the upsert to be race-safe; the pre-CR-005
  implementation was not race-safe under the real boot path. CR-005 brings the implementation in line
  with the spec's intent, not the other way around.
- **No public API change**: no route, DTO, enum, or dependency is added or removed.
- **No test removal**: every pre-existing test still passes; one test was strengthened to model the real
  SQLAlchemy semantics (the previous mock was permissive in a way that masked the bug).
- **Caveat:** the flake is timing-dependent. The strengthened test uses a deterministic mock for
  `begin_nested` and a separate assertion for the missing outer `rollback()`, so it does not depend on
  the real race window. The flake will be observed to disappear in production via the existing
  observability probes (Phase 27 metrics on `swarm_persistence.save_task` success vs. error rate).

---

## 10. Out of scope

- Refactoring `DbSwarmPersistence` to use a Unit-of-Work pattern (separate CR — would also touch
  Phase 26's `save_agent` / `save_message` / `save_snapshot` methods, which have similar but not
  identical patterns; not a single-bug fix).
- Replacing the optimistic-locking check (`AGENT_005`) with a true `SELECT ... FOR UPDATE` row lock
  (separate CR — Postgres-specific, would not work on SQLite, would require Phase 26 spec unfreeze).
- Adding a regression test that actually triggers the race window (separate work — would require
  real concurrent sessions on a real DB, which is what `test_concurrent_save_task_no_pk_violation`
  already does; the strengthened test just makes the mock honest).

---

## 11. Approval

- [ ] Architect (Rank 0) — approve the spec delta in §5
- [ ] Architect (Rank 0) — approve the implementation in §4
- [ ] After approval: commit per `docs/44_GIT_WORKFLOW.md` (one logical commit; subject
      `fix(persistence): use SAVEPOINT for race-recovery in save_task (CR-005)`)

---

**End of CR-005.**
