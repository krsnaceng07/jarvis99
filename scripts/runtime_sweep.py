"""Comprehensive runtime sweep — boot kernel in-process and probe every route.

Used to find latent 500s before declaring the API healthy.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("JARVIS_SYSTEM_ENVIRONMENT", "development")

from fastapi.testclient import TestClient  # noqa: E402

from api.main import create_app  # noqa: E402

app = create_app()

# Get a token first (login)
print("=== Boot + login ===")
with TestClient(app) as client:
    # Health
    h = client.get("/api/v1/health")
    print(f"  health: {h.status_code}  body={h.text[:200]}")

    # Login
    login = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "JarvisDev123!"},
    )
    print(f"  login: {login.status_code}  body={login.text[:200]}")
    token = None
    if login.status_code == 200:
        data = login.json()
        token = data.get("data", {}).get("access_token") or data.get("access_token")
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    # Probe every route
    print()
    print("=== Route sweep ===")
    failures = []
    for r in app.routes:
        if not hasattr(r, "methods") or not hasattr(r, "path"):
            continue
        methods = r.methods or set()
        if "/docs" in r.path or r.path.startswith(("/openapi", "/redoc", "/metrics")):
            continue
        # Substitute path params
        path = r.path
        for seg in [
            "{memory_id}",
            "{run_id}",
            "{workflow_id}",
            "{skill_id}",
            "{node_id}",
            "{task_id}",
            "{id}",
            "{identity_id}",
            "{goal_id}",
            "{mission_id}",
        ]:
            path = path.replace(seg, "probe-id")

        for method in methods:
            if method in ("HEAD", "OPTIONS"):
                continue
            try:
                if method == "GET":
                    resp = client.get(path, headers=headers)
                elif method == "POST":
                    # Try a minimal JSON body for POST. Most POST routes need
                    # real data; we'll just see if it's a 500 vs 4xx.
                    resp = client.post(path, headers=headers, json={})
                elif method == "PATCH":
                    resp = client.patch(path, headers=headers, json={})
                elif method == "PUT":
                    resp = client.put(path, headers=headers, json={})
                elif method == "DELETE":
                    resp = client.delete(path, headers=headers)
                else:
                    continue
                if 500 <= resp.status_code < 600:
                    failures.append((method, r.path, resp.status_code, resp.text[:300]))
                    print(f"  [FAIL] {resp.status_code} {method:6s} {r.path}")
                    print(f"         body: {resp.text[:250]}")
                else:
                    pass  # print(f"  [OK  ] {resp.status_code} {method:6s} {r.path}")
            except Exception as exc:
                failures.append((method, r.path, "EXC", str(exc)))
                print(f"  [EXC ] {method:6s} {r.path} -> {exc!r}")

    print()
    print(f"=== {len(failures)} runtime failures ===")
    out = ROOT / "audit_report.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(
            {
                "failures": [
                    {"method": m, "path": p, "status": s, "body": b}
                    for m, p, s, b in failures
                ],
                "total_routes": sum(
                    1
                    for r in app.routes
                    if hasattr(r, "methods") and hasattr(r, "path")
                ),
            },
            f,
            indent=2,
        )
    print(f"  report: {out}")
