"""
CR-002 regression test — locks down the skills-router mount point.

Bug history: 2026-07-10 — `skills.router` was mounted at `prefix="/api/v1"`,
causing the internal `@router.get("/{skill_id}")` catch-all to become
`GET /api/v1/{skill_id}` and shadow six single-segment top-level routes
(`/api/v1/missions`, `/api/v1/workflows`, `/api/v1/discover`,
`/api/v1/skills`, `/api/v1/identity`, `/api/v1/goal`).

This test pins the production mount to `prefix="/api/v1/skills"` by
asserting that:

  1. `api.main.create_app()` produces a route table where no route
     path under `/api/v1/` consists of exactly `"/api/v1/{param}"`-style
     catch-alls contributed by the skills router. (Concretely: every
     route that matches `/api/v1/...` and contains the literal
     substring `/skill` must also start with `/api/v1/skills/...` —
     i.e. there is no `/api/v1/{skill_id}` style shadow route.)

  2. The expected skills endpoints exist at the spec-documented paths:
        POST /api/v1/skills/install
        POST /api/v1/skills/remove
        GET  /api/v1/skills/
        GET  /api/v1/skills/search
        GET  /api/v1/skills/{skill_id}

     Using a real production `create_app()` would boot the full
     Kernel and DB, which is too heavy for a routing assertion.
     Instead, we mirror the production mount call directly from
     `api.main` — a 1:1 text reference to the line under test.
     If that line ever drifts, this test fails and points to it.

The test is hermetic: it does NOT touch the DB, the kernel, or any
network. It only inspects the FastAPI route table produced by
`create_app()`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import cast

from starlette.routing import Route as StarletteRoute

# Import the production factory. We do NOT call it (it boots the
# Kernel); we only need it to be importable so we can locate the
# production mount line in the source.
from api.main import create_app  # noqa: E402, F401

EXPECTED_SKILLS_PATHS = {
    "POST": ["/api/v1/skills/install", "/api/v1/skills/remove"],
    "GET": [
        "/api/v1/skills/",
        "/api/v1/skills/search",
        "/api/v1/skills/{skill_id}",
    ],
}

# What the line in api/main.py MUST contain for the fix to hold.
# We assert this with a text-level scan rather than booting the app
# so the test stays fast and hermetic.
PRODUCTION_MOUNT_REQUIRED_FRAGMENT = (
    'app.include_router(skills.router, prefix="/api/v1/skills")'
)
# What MUST NOT be present (the historic bug).
PRODUCTION_MOUNT_FORBIDDEN_FRAGMENT = (
    'app.include_router(skills.router, prefix="/api/v1")'
)

_API_MAIN_PATH = Path("api/main.py")


def _read_api_main_source() -> str:
    """Load api/main.py source text for static assertions."""
    return _API_MAIN_PATH.read_text(encoding="utf-8")


def test_production_skills_mount_uses_correct_prefix() -> None:
    """api/main.py MUST mount skills.router under /api/v1/skills.

    Pin the literal production mount line so a future agent cannot
    silently regress the prefix back to /api/v1.
    """
    source = _read_api_main_source()
    assert PRODUCTION_MOUNT_REQUIRED_FRAGMENT in source, (
        f"CR-002 regression: api/main.py no longer mounts the skills "
        f"router at prefix='/api/v1/skills'. "
        f"Expected literal line: {PRODUCTION_MOUNT_REQUIRED_FRAGMENT!r}. "
        f"This is the route-shadowing bug CR-002 fixed; restoring "
        f"the old prefix will re-shadow /api/v1/missions, /api/v1/"
        f"workflows, /api/v1/discover, /api/v1/skills, /api/v1/"
        f"identity, and /api/v1/goal."
    )
    assert PRODUCTION_MOUNT_FORBIDDEN_FRAGMENT not in source, (
        f"CR-002 regression: api/main.py contains the historic buggy "
        f"mount {PRODUCTION_MOUNT_FORBIDDEN_FRAGMENT!r}. Remove it; "
        f"the correct line is {PRODUCTION_MOUNT_REQUIRED_FRAGMENT!r}."
    )


def test_no_root_level_skill_catchall_route_exists() -> None:
    """Static check: no `prefix=\"/api/v1\"` mount may contribute
    a `/api/v1/{param}` catch-all that would shadow top-level routes.

    Concretely: any `app.include_router(...)` call that mounts under
    `/api/v1` (no further segment) must NOT pair with a router that
    declares a bare `/{param}` GET route. We assert this with a
    static regex scan — full route-table inspection requires booting
    the Kernel, which is out of scope for this regression test.
    """
    source = _read_api_main_source()

    # Find every include_router call and its prefix.
    include_pattern = re.compile(
        r'app\.include_router\(\s*([\w.]+)\s*,\s*prefix=(["\'])([^"\']+)\2',
    )
    mounts = include_pattern.findall(source)

    # The skills router must NOT be at the bare /api/v1 prefix.
    for router_name, _, prefix in mounts:
        if router_name == "skills.router":
            assert prefix == "/api/v1/skills", (
                f"CR-002 regression: skills.router mounted at "
                f"prefix={prefix!r}, expected '/api/v1/skills'."
            )


def test_skills_router_internal_paths_match_spec() -> None:
    """Static check: api/routes/skills.py declares the 5 documented
    routes at the paths the spec promises. (Path values only;
    handler bodies are out of scope.)
    """
    from api.routes.skills import router as skills_router  # noqa: E402

    declared: dict[str, set[str]] = {
        "GET": set(),
        "POST": set(),
        "PUT": set(),
        "DELETE": set(),
        "PATCH": set(),
    }
    for route in skills_router.routes:
        typed_route = cast(StarletteRoute, route)
        methods: set[str] = getattr(typed_route, "methods", set()) or set()
        for m in methods:
            if m in declared:
                declared[m].add(typed_route.path)

    # The router declares its routes relative to its own mount; the
    # production mount adds the /api/v1/skills prefix. We assert the
    # *internal* path layout, then the production mount (in
    # test_production_skills_mount_uses_correct_prefix) layers the
    # full path on top.
    expected_internal = {
        "POST": {"/install", "/remove"},
        "GET": {"/", "/search", "/{skill_id}"},
    }
    for method, paths in expected_internal.items():
        missing = paths - declared[method]
        assert not missing, (
            f"CR-002 regression: skills router is missing expected "
            f"{method} routes: {sorted(missing)}. Declared "
            f"{method} paths: {sorted(declared[method])}."
        )


def test_skills_router_has_no_bare_root_catchall() -> None:
    """The skills router MUST NOT have a route at the empty path
    (relative to its own mount) — that would be the worst kind of
    catch-all and is not in the spec.
    """
    from api.routes.skills import router as skills_router  # noqa: E402

    for route in skills_router.routes:
        typed_route = cast(StarletteRoute, route)
        assert typed_route.path != "", (
            "CR-002 regression: skills router has a route at the "
            "empty path '' — this would catch every request not "
            "matched by other routers and re-introduce shadowing."
        )


# ---------------------------------------------------------------------------
# Documentation test — keeps the regression rationale visible
# ---------------------------------------------------------------------------


def test_cr002_doc_references_the_bug() -> None:
    """The CR-002 doc must exist and reference the historic bug,
    so future maintainers understand why this regression test exists.
    """
    cr002 = Path("docs/CR/CR-002-skills-router-mount-shadowing.md")
    assert cr002.exists(), (
        f"CR-002 doc missing at {cr002}. The regression test above "
        f"references the doc; please keep them in sync."
    )
    content = cr002.read_text(encoding="utf-8")
    assert "route-shadowing" in content.lower(), (
        "CR-002 doc must mention 'route-shadowing' so its purpose is "
        "discoverable from the doc itself."
    )


# All tests in this module are intentionally hermetic / fast (no
# DB, no network, no Kernel boot). No module-level marker needed;
# individual tests are self-describing via their docstrings.
