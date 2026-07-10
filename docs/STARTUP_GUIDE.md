# JARVIS OS — Golden Startup Guide

**Status:** Active (Platform Infrastructure)
**Audience:** Anyone who needs to start, validate, or debug JARVIS from scratch.
**Last updated:** 2026-07-10

This document is the **single authoritative startup reference** for JARVIS OS.
If any other doc, README, or chat message disagrees with this file, **this file wins.**

---

## 1. The 10-Step Golden Startup Path

JARVIS must always be started the same way — locally, on a server, in CI, or inside
a Docker container. The path is fixed:

```
STEP 1  Clone the repository            (one-time)
STEP 2  Bootstrap the virtualenv       uv sync
STEP 3  Provide configuration          config.yaml
STEP 4  Initialize / migrate the DB    (automatic on boot)
STEP 5  Seed default admin + roles     (automatic on boot, dev env only)
STEP 6  Boot the Kernel                (automatic on boot)
STEP 7  Start the API gateway          uvicorn api.main:app
STEP 8  Verify health                  GET /api/v1/health → 200
STEP 9  Login                          POST /api/v1/auth/login
STEP 10 Run capability matrix          python scripts/validate_startup.py
```

Steps 1–3 are one-time setup. Steps 4–7 happen automatically when you run
`python run.py`. Steps 8–10 are validation — every time.

---

## 2. Quickstart (TL;DR)

### Windows (PowerShell)

```powershell
# One-time
git clone <jarvis-repo>                # STEP 1
cd jarvis
uv sync                                # STEP 2 — creates .venv and installs deps

# Each session — start JARVIS
python .\run.py                        # runs api.main:app on 127.0.0.1:8765
```

### macOS / Linux (bash)

```bash
# One-time
git clone <jarvis-repo>                # STEP 1
cd jarvis
uv sync                                # STEP 2

# Each session — start JARVIS
python3 run.py                         # runs api.main:app on 127.0.0.1:8765
```

---

## 3. What `run.py` does (and does NOT do)

`run.py` is a thin launcher. It does **not** contain business logic. It enforces
the canonical startup sequence:

1. **Preflight checks** (skippable via `--no-preflight`)
   - `config.yaml` exists at the project root.
   - `.venv` exists (`.venv/Scripts/python.exe` on Windows, `.venv/bin/python` on Unix).
   - The target port is not already bound.
2. **Resolves the uvicorn command** using the venv interpreter.
3. **Spawns uvicorn as a subprocess** with `JARVIS_CONFIG_PATH` set.

If preflight fails, you get an explicit error message and a non-zero exit code.
The script never silently falls back — that hides problems.

### Exit codes

| Code | Meaning |
|------|---------|
| 0    | uvicorn exited cleanly (0 means Ctrl+C clean shutdown) |
| 2    | Config file not found |
| 3    | Virtualenv missing — run `uv sync` |
| 4    | Target port already in use |
| 127  | uvicorn binary not found |

### Common flags

```bash
python run.py --port 9000              # change bind port
python run.py --config prod.yaml       # use a different config file
python run.py --reload                 # auto-reload on code changes (dev only)
python run.py --no-preflight           # skip preflight (CI / containers)
python run.py --print-only             # print resolved command and exit
```

---

## 4. Configuration

JARVIS reads two layers of configuration, in order of precedence:

1. **Environment variables** (`JARVIS_*`) — highest priority.
2. **`config.yaml`** at the project root — defaults.

The committed `config.yaml` is a **SQLite fallback for local development**.
Production should override via env vars (`JARVIS_DATABASE_HOST`, etc.) — see
`.env.example`.

The development seed admin is created automatically on first boot:

| Field    | Default             |
|----------|---------------------|
| Username | `admin`             |
| Password | `JarvisDev123!`     |
| Role     | `admin` (full RBAC) |

Override via `JARVIS_SECURITY_ADMIN_USERNAME` / `JARVIS_SECURITY_ADMIN_PASSWORD`.

---

## 5. What boot actually does

When `api.main:app` starts, the FastAPI lifespan handler:

1. Instantiates `Kernel()` and calls `initialize()`.
2. Registers `HealthMonitor`, `CapabilityRegistry`, and `TelemetryBroadcaster`.
3. Calls `kernel.boot(config_path)` which:
   - Loads the security vault.
   - Initializes the in-process event bus.
   - Loads `Settings` from `config.yaml`.
   - Registers all core services in the DI container (orchestrator, runtime,
     reasoning engine, memory, observability, identity, goal, mission,
     skill components, etc.).
   - Triggers the `SecuritySeedService` to seed default permissions, roles,
     and the development admin (only when `JARVIS_SYSTEM_ENVIRONMENT=development`).
4. Registers the dynamic skill components (registry, validator, signer,
   sandbox, permission engine, installer).
5. Wires observability routes to the resolved service.
6. Triggers the resume manager for in-flight mission recovery (Phase 15).
7. Starts the `HealthMonitor` background loop (15s heartbeat).
8. Serves HTTP on the configured host:port.

On `Ctrl+C` or `SIGTERM`, the shutdown sequence reverses the order:
`HealthMonitor.stop` → `Kernel.stop_all` → `Kernel.shutdown`.

---

## 6. Verifying a clean start

After starting JARVIS, the three minimum checks are:

```bash
# 1. Health endpoint
curl -s http://127.0.0.1:8765/api/v1/health
#   → {"success": true, "data": {"status": "healthy", "version": "0.1.0", ...}, ...}

# 2. Admin login
curl -s -X POST http://127.0.0.1:8765/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username":"admin","password":"JarvisDev123!"}'
#   → {"success": true, "data": {"access_token": "...", "refresh_token": "..."}, ...}

# 3. Capability matrix (probes every major endpoint)
python scripts/validate_startup.py
```

If all three pass, the system is verifiably running. Anything else is a real bug.

---

## 7. Programmatic startup (for tests & tooling)

Use `scripts/golden_startup.py` when you need to boot JARVIS from inside Python:

```python
from scripts.golden_startup import (
    StartupConfig,
    preflight_checks,
    run_inprocess_healthcheck,
    wait_for_health,
    boot_kernel,
)
import asyncio

# 1) Preflight only (no side effects)
cfg = StartupConfig(port=8765)
result = preflight_checks(cfg)
assert result.ok, result.error

# 2) In-process healthcheck (fast, used by tests)
result = asyncio.run(run_inprocess_healthcheck(timeout_seconds=30))
assert result.ok, result.error

# 3) Wait for an externally-spawned JARVIS instance to come up
result = asyncio.run(wait_for_health("http://127.0.0.1:8765"))

# 4) Boot the kernel directly (no HTTP)
kernel = asyncio.run(boot_kernel())
```

---

## 8. Common failure modes (and fixes)

| Symptom | Cause | Fix |
|---------|-------|-----|
| `failed to locate pyvenv.cfg` | `.venv` broken | Delete `.venv/`, run `uv sync` |
| `port 8765 already in use` | zombie uvicorn | `Stop-Process -Id <pid> -Force` on Windows; `pkill -f uvicorn` on Unix |
| `config not found` | wrong CWD | `cd` to the repo root before running |
| `/health` returns 503 | DB unreachable | check `config.yaml` → `database.host` |
| Login returns AUTH_004 | seed not run | set `JARVIS_SYSTEM_ENVIRONMENT=development` and restart |
| `ModuleNotFoundError` | venv not active | run `run.py` (it picks the venv automatically) |

---

## 9. What is NOT in scope for `run.py`

- Production WSGI/ASGI server tuning (use gunicorn/uvicorn workers directly).
- Container entrypoint (use the dedicated Dockerfile when added).
- Auto-restart / process supervision (use systemd, supervisord, or a container orchestrator).
- TLS termination (terminate at nginx / a load balancer).
- Database migrations beyond what `Kernel.boot` does on startup (use Alembic for schema changes).

---

## 10. Related tools

| Tool | Purpose |
|------|---------|
| `scripts/validate_startup.py` | One-command full validation (boot + health + login + capability matrix). |
| `scripts/capability_matrix.py` | Generate the capability matrix report (Markdown + JSON). |
| `scripts/golden_startup.py` | Programmatic startup API (used by tests). |
| `scripts/quality_gate.py` | Run ruff + mypy + pytest + coverage. |
| `scripts/architecture_linter.py` | Verify frozen architecture boundaries. |

---

*Authority: This document is the canonical startup reference. If `README.md`,
`AGENTS.md`, or any chat session gives different instructions, follow this file.*