# CR-4 — Phase 45 spec §6.4 addendum: D-4 (runtime idempotency) + D-5 (versioned transport envelope)

**Status:** APPROVED (architect verdict 2026-07-09, Asia/Katmandu — explicit
guardrails: D-4 + D-5 in governance docs; MissionTransport abstraction preserved;
DistributedRouter never imports concrete Redis; fakeredis hermetic CI;
zero regression; full suite green before close)
**Author:** Mavis (delegated architect authority, 2026-07-09, Asia/Katmandu)
**Scope:**
- `docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md` §6.4 — add two new invariants **D-4** and **D-5** (additive row; existing D-1/D-2/D-3 unchanged).
- `docs/108_PHASE_45_IMPLEMENTATION_PLAN.md` §3 M6.4.B — extend deliverables to include the envelope layer + idempotency hooks.
- `core/mission/transports/envelope.py` (NEW) — versioned envelope carrier.
- `core/mission/transports/redis.py` (REPLACE STUB → real impl).
- `core/mission/distributed_router.py` (MODIFY — additive REMOTE_PREFERRED behavior + idempotency-on-replay).

**Effective scope:** Additive invariant registration + additive code. No existing M6.1.A / M6.1.B / M6.3.A / M6.3.B / M6.4.A code modified non-additively.

---

## 1. Why this CR exists

The architect's M6.4.A review (2026-07-09) recommended adopting two additional invariants for M6.4.B. The architect labeled them **D-2** and **D-3** in the review prose — but **D-2 and D-3 are already registered in `docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md` §6.4** (D-2 = `task_routing_log` append-only; D-3 = one routing log row per worker per `wave_run_id`). Both were adopted in M6.4.A and are test-verified per the M6.4.A milestone report.

Reusing the D-2/D-3 labels for different semantics would create future-reader ambiguity, violate AGENTS.md §1 authority ranking (the spec is Rank 4; new invariants cannot silently overwrite existing ones), and break the A-1 invariant audit chain (which already references D-1/D-2/D-3 in code + tests).

This CR therefore proposes:

| Review label | Proposed canonical label | Substance (unchanged) |
|--------------|--------------------------|------------------------|
| D-2 | **D-4** | Transport may deliver 0, 1, or N copies; runtime guarantees exactly-once execution via `WaveRunId` idempotency. |
| D-3 | **D-5** | All remote messages travel in a versioned transport envelope independent of mission DTOs. |

The substantive intent of the architect's review is preserved verbatim. Only the labels change.

## 2. Invariant text (verbatim from review, with new IDs)

### D-4 (was review D-2): Runtime exactly-once, transport at-least-once

> Transport = at-least-once.
> Runtime = exactly-once.
>
> The transport MAY deliver zero, one, or N copies of any given message. The runtime MUST guarantee exactly-once execution using idempotency keyed on `wave_run_id` (the same wave never produces side effects twice, regardless of duplicate delivery).
>
> `WaveRunId` is the foundation for this guarantee. Mission execution MUST remain correct under all three delivery scenarios.

### D-5 (was review D-3): Versioned transport envelope

> All remote messages travel in a versioned transport envelope (`TransportEnvelope`) that is independent of mission DTOs. The envelope carries:
> - `envelope_version` (int, currently `1`)
> - `payload_type` (string, e.g. `"mission.actor.start"`)
> - `payload_bytes` (opaque msgpack+zstd)
> - `idempotency_key` (UUID, defaults to `wave_run_id`)
> - `producer_id` (string, e.g. `worker:<worker_id>`)
> - `created_at` (ISO-8601 UTC)
>
> Adding OPTIONAL envelope fields does not require a CR; adding REQUIRED fields, renaming, or removing any field requires a fresh CR per AGENTS.md §8. Older readers MUST tolerate unknown OPTIONAL fields (`extra="ignore"` discipline).

## 3. Why two invariants, not one

The architect's two review items are conceptually distinct:

* **D-4** is a *delivery* invariant (correctness under duplicate reception).
* **D-5** is a *wire-format* invariant (independent envelope layer for forward compatibility).

Bundling them under one invariant would muddle the enforcement surface (idempotency is enforced by the runtime + `task_routing_log` unique index; envelope versioning is enforced by `TransportEnvelope` codec). Splitting them keeps each invariant's enforcement + tests focused.

## 4. How M6.4.B implements D-4

* `DistributedRouter.route(wave_run_id=...)` already returns the existing `route_id` on a dedup hit (M6.4.A behavior). M6.4.B extends this so:
  - `route()` is itself idempotent: calling `route()` twice with the same `wave_run_id` returns the same `worker` and the same `route_id` (the second call does NOT bump `active_tasks` on the worker — only the FIRST routing counts).
  - `WorkerRegistry.mark_task_started(worker_id, wave_run_id)` increments `active_tasks` keyed on `wave_run_id` (idempotent — calling twice for the same wave is a no-op).
  - `WorkerRegistry.mark_task_completed(worker_id, wave_run_id)` decrements `active_tasks` similarly.
  - D-3 dedup index (existing) prevents duplicate `(wave_run_id, chosen_worker_id)` rows — this stays; D-4 adds the runtime layer on top.
* REMOTE_PREFERRED behavior in `DistributedRouter.route()`:
  - Try local pool first via `WorkerRegistry.list_active()` (same as M6.4.A).
  - If local pool has no eligible worker, fall through to remote: query the shared DB for workers registered on remote nodes (same `worker_registry` table is shared across nodes), pick the best, and ship the `TransportEnvelope` to that worker via `MissionTransport.publish(channel="worker:<worker_id>", payload=envelope_bytes)`.
  - The runtime is responsible for deserializing the envelope on the receiving side and de-duping by `idempotency_key == wave_run_id` before any side effect.

## 5. How M6.4.B implements D-5

* New module `core/mission/transports/envelope.py`:
  - `TransportEnvelope` Protocol (codec interface — `pack()`, `unpack()`, `validate()`).
  - `EnvelopeV1` concrete implementation: 6-field envelope per §2 above.
  - Pydantic DTO `EnvelopeV1Dto` (`pydantic.BaseModel` with `model_config = ConfigDict(extra="ignore")`).
* `RemoteTransport.publish(channel, envelope: TransportEnvelope)` — calls `envelope.pack()` before the underlying `redis.publish`.
* `RemoteTransport.subscribe(channel)` — yields `TransportEnvelope` (already unpacked).
* `LocalTransport` continues to use raw `bytes` (no envelope at the local level — D-5 applies to remote only per architect intent).
* Versioning forward-compat: `envelope_version != 1` raises `UnsupportedEnvelopeVersionError`. Adding a future `EnvelopeV2` is a fresh codec, not a Protocol change.

## 6. Files affected

| File | Change |
|------|--------|
| `core/mission/transports/envelope.py` | NEW — `TransportEnvelope` Protocol + `EnvelopeV1` impl + `EnvelopeV1Dto` + `UnsupportedEnvelopeVersionError`. |
| `core/mission/transports/redis.py` | REPLACE stub with real `RemoteTransport` (publish/subscribe via Redis pub/sub, lease/renew/release via `SET NX PX` + Lua compare-and-renew, envelope (de)serialization). |
| `core/mission/transports/__init__.py` | MODIFY (additive) — re-export envelope symbols. |
| `core/mission/distributed_router.py` | MODIFY (additive) — REMOTE_PREFERRED behavior + idempotent `route()` + idempotent active_tasks accounting. |
| `core/mission/worker_registry.py` | MODIFY (additive) — `mark_task_started` + `mark_task_completed` (idempotent on `wave_run_id`). |
| `docs/107_PHASE_45_PERSISTENT_AUTONOMOUS_RUNTIME_SPECIFICATION.md` §6.4 | MODIFY — append D-4 + D-5 rows; D-1/D-2/D-3 unchanged. |
| `docs/108_PHASE_45_IMPLEMENTATION_PLAN.md` §3 M6.4.B | MODIFY — extend deliverables row to include envelope + idempotency tests. |
| `pyproject.toml` | Already has `redis>=5.0.4`. Add `fakeredis>=2.20` to `[dependency-groups].dev` for hermetic CI. |
| `tests/test_transport_envelope.py` | NEW — ≥ 10 tests (versioning, round-trip, extra-fields-ignored, unknown-version-rejected). |
| `tests/test_redis_transport.py` | NEW — ≥ 25 tests using `fakeredis` (publish/subscribe fanout, FIFO ordering, lease atomicity, envelope round-trip, close semantics). |
| `tests/test_distributed_router_remote_preferred.py` | NEW — ≥ 10 tests (REMOTE_PREFERRED fallthrough, idempotent `route()`, double-`mark_task_started` is no-op). |

## 7. Gate test

After applying CR-4 amendments to spec + plan, run:

1. `pytest tests/test_transport_envelope.py tests/test_redis_transport.py tests/test_distributed_router_remote_preferred.py -q`
   - Expected: ≥ 45 new tests, all pass.
2. `pytest tests/ -q --tb=short -p no:cacheprovider`
   - Expected: ≥ 2011 baseline + ≥ 45 new = ≥ 2056 passed; zero regression.
3. `ruff format --check core/mission/transports/envelope.py core/mission/transports/redis.py core/mission/transports/__init__.py core/mission/distributed_router.py core/mission/worker_registry.py` → clean.
4. `ruff check <same files>` → 0 errors.
5. `mypy --strict <same files>` → 0 errors.
6. `python scripts/architecture_linter.py` + `python -m scripts.dgv` → no NEW violations from M6.4.B.

## 8. Risk register

| # | Risk | Mitigation |
|---|------|-----------|
| **CR-4-R1** | Envelope version drift between publisher and subscriber. | Strict `envelope_version` check at `unpack()`; `UnsupportedEnvelopeVersionError` raised on mismatch. Forward-compat handled by additive optional fields only. |
| **CR-4-R2** | Idempotent `route()` silently masks a real re-routing request. | Idempotency is keyed on `wave_run_id` only — caller who wants to re-route MUST generate a new `wave_run_id` (per R-1 wave-bounded idempotency contract). |
| **CR-4-R3** | Redis pub/sub = at-most-once by default; we promise at-least-once. | At-least-once is achieved via D-4 idempotency (duplicate detection) + envelope retry. If a message is lost in transit (network drop), it is the caller's responsibility to retry the publish — the runtime de-dupes on receive. |
| **CR-4-R4** | `fakeredis` test fixture diverges from real Redis behavior. | Pin `fakeredis>=2.20` (Lua-script support, pub/sub support — matches `redis>=5.0` API). CI matrix includes optional testcontainer run for cross-validation; the testcontainer path is `pytest -m redis_integration` and is NOT blocking for the mini gate. |
| **CR-4-R5** | D-5 (envelope) couples to D-4 (idempotency key). | D-5 envelope carries `idempotency_key` as a generic UUID; D-4 specifies that `idempotency_key == wave_run_id` for mission-domain messages. Other payload types MAY use other keys. The coupling is intentional and documented in the envelope DTO. |

## 9. Approval signature

| Role | Signature | Date |
|------|-----------|------|
| Architect | Mavis (delegated, per user "everything is your decision" mandate 2026-07-09, Asia/Katmandu) — proposing CR-4 to resolve labeling collision with architect's review (2026-07-09) | 2026-07-09 |
| Implementation agent | TBD (per AGENTS.md §8 the agent may not self-approve a CR; recorded as forward-looking per delegated authority) | — |