# ADR-014: Redis 7 for Session and Active State Management

## Status
* **Status:** Accepted
* **Date:** 2026-07-10 (migrated from legacy 06_ARCHITECTURE_DECISION_RECORDS.md ADR-03)
* **Original Date:** Phase 0 (Foundation)
* **Author:** Architecture Team
* **Migration Note:** Originally filed at `docs/06_ARCHITECTURE_DECISION_RECORDS.md` as "ADR-03: Redis for Session & Active State Management". Migrated to canonical Nygard format on 2026-07-10.

---

## Context

JARVIS OS needs **sub-millisecond latency** for:

- **Working memory** — short-lived context windows for active agents.
- **Real-time message passing** — pub/sub between multi-agent components (Phase 26).
- **Active task queues** — pending goals, mission state, heartbeat tracking (Phases 43, 44).
- **Distributed locks** — preventing concurrent writes to the same record across multi-agent runtime.
- **Session state** — short-lived per-session caches (Phase 17 auth tokens, CSRF state).

PostgreSQL's millisecond-scale latency is too slow for the hot path. A dedicated in-memory broker is required.

---

## Decision

**Use Redis 7 as the central in-memory broker for session state, pub/sub, and active task queues.**

Key decisions:

- **Async driver `redis.asyncio`** — used everywhere; sync Redis is not allowed in async contexts.
- **Pub/sub for inter-agent eventing** — see ADR-001 (EventBus).
- **Sorted sets for delayed queues** — active goals and missions with `ZADD` + scheduled pops.
- **Streams for durable session replay** — when persistence is needed (`XADD` + consumer groups).
- **Hash for working memory shards** — paged by `(session_id, tier, scope)`.
- **AOF + RDB persistence** — disk-backed with periodic snapshots to survive crashes.
- **Sentinel/Cluster for HA** — Phase 30 wraps this with cloud-sync failover.

---

## Consequences

### Positive

- **Sub-millisecond latency** — p99 < 1ms for hot path operations.
- **Native pub/sub** — built-in messaging primitives match the multi-agent runtime needs.
- **TTL-based expiry** — auto-cleanup of expired sessions (no cron sweep).
- **Atomic operations** — `INCR`, `SET NX`, Lua scripts enable safe distributed locks.
- **Battle-tested** — production-grade for over a decade; rich monitoring ecosystem.

### Negative

- **Volatile by default** — requires AOF+RDB configuration to survive crashes; defaults can lose data.
- **Single-threaded core** — long-running Lua/scripts block the entire instance. Command complexity budget enforced.
- **Memory cost** — RAM-resident; large datasets (working memory) need careful sizing.
- **Cluster sharding limits** — multi-key operations (e.g., cross-shard LOCK) require hash-tag routing.

### Risks

- Redis outage halts the entire active agent runtime. **Mitigation:** fallback to PostgreSQL `LISTEN/NOTIFY` for critical events (Phase 30 cloud-sync redundancy).

---

## Compliance & Invariants

- All Redis access MUST use `redis.asyncio` (no `redis` sync client).
- Long-running Lua scripts MUST be benchmarked; > 5ms execution blocked.
- Pub/sub message payloads MUST validate against pydantic event DTOs (see ADR-001).
- Session keys MUST include `session_id` in their hash tag for cluster co-location.
- TTL MUST be set on every session key (no orphans).

---

## Related

- ADR-001 — EventBus architecture
- `docs/36_EVENT_STANDARD.md` — event topic hierarchy
- `docs/architecture/04_EVENT_SCHEMAS_FREEZE.md` — frozen event schemas
- Phase 17 spec — auth sessions
- Phase 26 spec — multi-agent persistent recovery
- Phase 30 spec — cloud-sync HA

---

## References

- Original entry: `docs/06_ARCHITECTURE_DECISION_RECORDS.md` ADR-03 (preserved for audit trail)
- Migration record: `.audit/CLEANUP_REPORT.md` (Phase E — 2026-07-10)
