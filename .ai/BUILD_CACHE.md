# BUILD CACHE

*Rule: If changed file is not related to build tools, do NOT run them again. Re-run affected-file gates only.*

**Last Ruff:** PASS (on `phase45/transport` at `7e53c69`; ruff format + ruff check clean per M6.4.A + M6.4.B.2 milestone reports)
**Last Mypy:** PASS (mypy --strict clean on 12 production files in M6.4.A; clean on 2 production files in M6.4.B.2)
**Last Pytest:** PASS (1985 passed / 2 skipped / 0 failed; +224 new M6.4 tests on top of 1761 baseline)
**Coverage:** 91.00% (target ≥ 80% met; security-relevant modules at 100%)

**Affected test set (M6.4):**
- tests/test_transport_envelope.py (39 tests, M6.4.B.1)
- tests/test_local_transport_exhaustive.py (45 tests, M6.4.A)
- tests/test_worker_registry.py (22 tests, M6.4.A)
- tests/test_distributed_router.py (21 tests, M6.4.A)
- tests/test_distributed_pool_route.py (13 tests, M6.4.A)
- tests/test_worker_process.py (28 tests, M6.4.A)
- tests/test_remote_transport_exhaustive.py (56 tests, M6.4.B.2)

**Dev dep pins (M6.4.B.2):**
- `fakeredis>=2.20` (Lua-backed fakeredis requires lupa)
- `lupa>=2.0`
- `redis>=5.0.4` (already in M6.4.A baseline)
