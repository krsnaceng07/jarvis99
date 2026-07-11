# PHASE 45 M6.4.B REPORT

## Milestone Summary
Completed: M6.4.B code-completion — DistributedRouter REMOTE_PREFERRED
behaviour (publishes EnvelopeV1 over MissionTransport) +
WorkerRegistry.mark_task_started / mark_task_completed (idempotent
task accounting on the receiver side).
Date: 2026-07-11

## Scope (per `docs/108_PHASE_45_IMPLEMENTATION_PLAN.md` §3 M6.4.B)
- `DistributedRouter._route_remote`: when wired with a `MissionTransport`,
  picks the best eligible worker (load-aware), builds an `EnvelopeV1`
  (D-5), publishes it to the worker's channel, and records a
  `ROUTED_REMOTE` row in `task_routing_log` (D-2). When the transport
  is `None`, preserves the M6.4.A contract (journal row +
  `RemoteTransportNotImplementedError`).
- `WorkerRegistry.mark_task_started`: idempotent on
  `(worker_id, wave_run_id)`. Increments `active_tasks` exactly once
  per in-flight wave. Returns `False` for missing routing rows or
  already-completed waves.
- `WorkerRegistry.mark_task_completed`: idempotent on duplicate calls.
  Sets `task_routing_log.completed_at` once; decrements `active_tasks`
  with a zero-floor guard.
- `core/mission/transports/envelope.py` — bug fix: `pack()` now uses
  `model_dump()` + explicit `UUID → str` coercion (pydantic 2.13.4's
  `mode="json"` raises `UnicodeDecodeError` on `bytes` fields;
  msgpack payloads are never valid UTF-8). The round-trip on
  `unpack()` is symmetric (`model_validate` accepts `str` for a
  `UUID` field).

## Files Modified
- `core/mission/distributed_router.py`: REMOTE_PREFERRED policy
  implementation (`_route_remote`, `REASON_ROUTED_REMOTE`,
  `RemoteTransportNotImplementedError` doc update, A-1 invariant
  narrative for the publish path). 305 lines added, 28 deleted.
- `core/mission/worker_registry.py`: `mark_task_started` /
  `mark_task_completed` (idempotent on `(worker_id, wave_run_id)`,
  keyed on `task_routing_log` row). 208 lines added, ~3 deleted.
- `core/mission/transports/envelope.py`: `pack()` switched to
  `model_dump()` + `UUID → str` coercion (pydantic 2.13.4 bug fix).
  Module docstring updated to match the new wire pipeline. ~15 lines
  changed.
- `tests/test_distributed_router_remote_preferred.py`: NEW, 23 tests
  across 8 test classes covering the REMOTE_PREFERRED path, the
  cross-client `RemoteTransport` round-trip, the receiver-side task
  accounting, and the A-1 architect invariant.

## Responsibilities
- `DistributedRouter._route_remote` owns the leader-side REMOTE_PREFERRED
  decision: capability filter → load-aware pick → `EnvelopeV1` build
  → `MissionTransport.publish` → `task_routing_log` insert (D-2/D-3).
- `WorkerRegistry.mark_task_started` / `mark_task_completed` own the
  receiver-side active_tasks accounting, idempotent under
  `mark_task_*` duplicate calls (D-4 at-least-once).
- `EnvelopeV1.pack` / `unpack` own the v1 wire-format round-trip:
  msgpack + zstd of the Pydantic DTO (with `UUID` as `str` for
  msgpack interop).

## Architecture Impact
- Additive only. No changes to any FROZEN interface, DTO shape, or
  protocol. The router still speaks only to the `MissionTransport`
  Protocol (A-1 invariant preserved — verified by an AST inspection
  test in the new test file).
- No CR required. The spec/plan were not amended; the `envelope.py`
  change is a bug fix to make the M6.4.B.1 wire pipeline actually
  function with binary payloads (the pydantic 2.13.4 `mode="json"`
  failure on `bytes` is an upstream-library regression that the
  v1 codec was silently tripping over).

## Public Interface Changes
- `DistributedRouter.__init__` gained a `transport: Optional[Any] = None`
  parameter (the M6.4.A stub was `transport=None` only). The router
  never imports a concrete transport class; the parameter is typed
  `Any` so the duck-typed call site (`self._transport.publish`) is
  the only contract.
- `DistributedRouter._route_remote` — new private method (the public
  surface change is the REMOTE_PREFERRED behaviour, observable
  through the existing `route()` API).
- `WorkerRegistry.mark_task_started` / `mark_task_completed` — new
  public methods, additive.
- `REASON_ROUTED_REMOTE` — new public string constant.
- `RemoteTransportNotImplementedError` — class identity preserved
  (the M6.4.A test `test_remote_preferred_raises_not_implemented`
  still asserts on this exact class name).

## Tests Added
- 23 new tests in `tests/test_distributed_router_remote_preferred.py`:
  - `TestRemotePreferredWithoutTransport` (2): raises contract + journal audit
  - `TestRemotePreferredWithLocalTransport` (5): envelope publish,
    D-4 idempotency_key, D-5 payload round-trip, D-2 journal row, no-subscriber audit
  - `TestRemotePreferredPolicySemantics` (4): no-eligible-worker
    (raise / audit-return), load-aware pick, D-3 dedup
  - `TestRemotePreferredWithRedisTransport` (1): cross-client
    fakeredis round-trip (proves the wire path, not a same-process
    shortcut)
  - `TestMarkTaskStarted` (5): increment, idempotent on double call,
    no-routing-row → False, already-completed → False, arg validation
  - `TestMarkTaskCompleted` (4): decrement, idempotent on double
    call, no-routing-row → False, completed_at is set
  - `TestEndToEndLifecycle` (1): route → publish → start → complete
    active_tasks invariant
  - `TestA1NoConcreteTransportImport` (1): AST inspection — the
    router does NOT import `LocalTransport` / `RemoteTransport` /
    `MissionTransport` directly
- Plan §3 M6.4.B floor was ≥ 10 tests; this milestone ships 23 (130%
  of floor).

## Frozen Modules Touched
- `core/mission/transports/envelope.py` — bug fix to `pack()` /
  module docstring. The v1 codec was M6.4.B.1 work that landed at
  `1401b81` but had not been individually frozen. M6.4.B code-completion
  is in-scope for any defect that blocks the M6.4.B deliverables; the
  change is additive (no Protocol change, no DTO change, no wire-format
  field change — only a switch from a broken `mode="json"` to a
  working `model_dump()` + `UUID → str` coercion that produces the
  same on-wire bytes the design intended).
- No FROZEN interface module (per `docs/60_MASTER_INDEX.md` /
  `FREEZE_LEDGER`) was modified.

## Quality Gates
- Ruff format: ✅ Passed on all 4 changed files
- Ruff check: ✅ Passed on all 4 changed files (auto-fixed 8 I001
  import-ordering issues in the test file during dev)
- Mypy `--strict`: ✅ Passed on all 3 source files + the new test file
- Pytest: ✅ 23/23 new tests pass; 184/184 M6.4 test suite passes
  (router + transport + envelope); 1824/1824 pre-existing project
  tests pass (no regression). Total: **2008 passed, 2 skipped,
  0 failed**. Was 1985 on `phase45/transport` pre-M6.4.B
  (`337ca64` baseline). +23 net new.
- Architecture audit: ✅ A-1 invariant (router does not import
  concrete transport) verified by AST inspection in
  `TestA1NoConcreteTransportImport`.

## Gate Status
✅ PASS

## Open / Deferred (informational, not blockers)
- M6.4.C (leader election + horizontal scaling) — STRETCH per plan
  §3, deferrable; not in this milestone's scope.
- M6.1.B, M6.3.A, M6.3.B, M6.2.A, M6.2.B, M6.5.A, M6.5.B — other
  Phase 45 sub-milestones on separate branches; picked up after
  M6.4 freeze is approved.
- The `envelope.py` docstring at the top was updated to reflect the
  new `model_dump()` path. The M6.4.B.1 spec text (in
  `docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md`
  §6.4 D-5) uses the older "model_dump(mode=json)" wording but the
  spec is at the wire-format-intent level ("versioned, msgpack+zstd
  of an EnvelopeV1Dto"); the implementation fix is consistent with
  the intent. No spec amendment is required.

## Next Steps
Awaiting architect approval before:
1. Tagging `phase45/transport` as ready to merge to `main`
   (per AGENTS.md §1 rank-5 → rank-2 transition).
2. Picking up the next Phase 45 sub-milestone (M6.1.B, M6.3.A, or
   M6.4.C — architect's call).
