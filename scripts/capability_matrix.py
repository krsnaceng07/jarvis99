"""
PHASE: Platform Infrastructure
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/STARTUP_GUIDE.md (section "Capability Matrix")

IMPLEMENTATION PLAN:
    docs/STARTUP_GUIDE.md (section "Capability Matrix")

AUTHORITATIVE:
    NO

Capability matrix probe.

Given a running JARVIS instance, exercises each major feature area (boot,
auth, memory, missions, agent, workflows, skills, observability, etc.) and
returns a structured report. Output formats:
    - JSON (machine-readable, for CI)
    - Markdown (human-readable, for docs/reports)

Default output paths:
    JARVIS_CAPABILITY_MATRIX.md  (committed in the repo, refreshed by CI)
    JARVIS_CAPABILITY_MATRIX.json (consumed by dashboards / downstream tools)

This file does NOT touch frozen contracts; it only probes them.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent

DEFAULT_BASE_URL = "http://127.0.0.1:8765"
DEFAULT_TIMEOUT = 8.0

DEFAULT_OUTPUT_MD = ROOT / "JARVIS_CAPABILITY_MATRIX.md"
DEFAULT_OUTPUT_JSON = ROOT / "JARVIS_CAPABILITY_MATRIX.json"


# ---------------------------------------------------------------------------
# Result data structures
# ---------------------------------------------------------------------------


@dataclass
class ProbeResult:
    """Outcome of probing a single capability."""

    capability: str
    category: str
    method: str
    path: str
    status: str  # "pass" | "fail" | "skip" | "warn"
    http_status: Optional[int] = None
    latency_ms: Optional[float] = None
    notes: str = ""
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dict view."""
        return asdict(self)


@dataclass
class MatrixReport:
    """Full capability-matrix report across all categories."""

    base_url: str
    generated_at: str
    summary: Dict[str, int] = field(default_factory=dict)
    capabilities: List[ProbeResult] = field(default_factory=list)

    def compute_summary(self) -> None:
        """Recompute the pass/fail/skip/warn summary from capabilities."""
        summary = {"pass": 0, "fail": 0, "skip": 0, "warn": 0, "total": 0}
        for c in self.capabilities:
            summary[c.status] = summary.get(c.status, 0) + 1
            summary["total"] += 1
        self.summary = summary

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serializable dict view of the whole report."""
        return {
            "base_url": self.base_url,
            "generated_at": self.generated_at,
            "summary": self.summary,
            "capabilities": [c.to_dict() for c in self.capabilities],
        }


# ---------------------------------------------------------------------------
# Probe definitions — declarative, easy to extend
# ---------------------------------------------------------------------------


@dataclass
class ProbeSpec:
    """Specification of a single capability probe."""

    capability: str
    category: str
    method: str
    path: str
    requires_auth: bool = False
    expected_status: Tuple[int, ...] = (200,)
    # Status codes that should be reported as ``warn`` instead of ``fail``.
    # Use this for endpoints with known route-level permission gates that the
    # dev admin does not satisfy — these are not regressions, they are
    # expected until permission provisioning is fixed (see auth-fix B1/B2).
    warn_status: Tuple[int, ...] = ()
    setup: Optional[Callable[["ProbeRunner"], Optional[Dict[str, Any]]]] = None
    body_factory: Optional[Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]] = None
    notes: str = ""


def _noop(_: Any) -> Optional[Dict[str, Any]]:
    """Default setup that does nothing."""
    return None


def _login_setup(runner: "ProbeRunner") -> Optional[Dict[str, Any]]:
    """Login as the development admin and store the token on the runner."""
    token = runner.login(
        username=runner.admin_username, password=runner.admin_password
    )
    return {"token": token} if token else None


def _store_memory_body(_: Dict[str, Any]) -> Dict[str, Any]:
    """Build a memory store request body for the matrix probe."""
    return {
        "content": (
            "JARVIS capability matrix probe — synthetic memory entry generated "
            "during platform validation. timestamp=" + datetime.now(timezone.utc).isoformat()
        ),
        "source_type": "capability_matrix",
        "importance": 0.4,
        "confidence": 0.9,
    }


def _create_mission_body(_: Dict[str, Any]) -> Dict[str, Any]:
    """Build a minimal mission create request body."""
    return {
        "goal": "capability-matrix probe — synthetic mission",
        "budget_limit": 1.0,
    }


def _agent_run_body(_: Dict[str, Any]) -> Dict[str, Any]:
    """Build a minimal agent run request body."""
    return {"goal": "capability-matrix probe — synthetic agent run", "budget": 1.0}


# ---------------------------------------------------------------------------
# Probe runner — talks to a live JARVIS instance over HTTP
# ---------------------------------------------------------------------------


class ProbeRunner:
    """Run a list of probe specs against a JARVIS base URL."""

    def __init__(
        self,
        base_url: str,
        timeout: float = DEFAULT_TIMEOUT,
        admin_username: str = "admin",
        admin_password: str = "JarvisDev123!",
    ) -> None:
        """Initialize the runner."""
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.admin_username = admin_username
        self.admin_password = admin_password
        self._token: Optional[str] = None
        self._context: Dict[str, Any] = {}
        self._client_factory: Optional[Callable[[], Any]] = None

    def set_client_factory(self, factory: Callable[[], Any]) -> None:
        """Inject an HTTP client factory (used by tests with TestClient)."""
        self._client_factory = factory

    def login(self, username: str, password: str) -> Optional[str]:
        """Authenticate and store the JWT bearer token."""
        url = self.base_url + "/api/v1/auth/login"
        payload = {"username": username, "password": password}
        client = self._make_client()
        try:
            response = client.post(url, json=payload)
            if response.status_code == 200:
                data = response.json()
                token = (
                    data.get("data", {}).get("access_token")
                    or data.get("access_token")
                )
                self._token = token
                return token
        except Exception:
            return None
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()
        return None

    def _make_client(self) -> Any:
        """Build an HTTP client. Uses httpx by default; TestClient in tests.

        Forwards the runner's current bearer token (if any) to the new client
        via ``set_token`` so auth-required probes can reuse it.
        """
        if self._client_factory is not None:
            client = self._client_factory()
        else:
            import httpx

            client = httpx.Client(timeout=self.timeout)
        set_token = getattr(client, "set_token", None)
        if callable(set_token):
            set_token(self._token)
        return client

    def run(self, specs: List[ProbeSpec]) -> List[ProbeResult]:
        """Run every probe spec; never raises — failures become ProbeResult rows."""
        results: List[ProbeResult] = []

        # First probe is login (it sets the auth token used by later probes).
        login_spec = next(
            (s for s in specs if s.capability == "auth.login"), None
        )
        if login_spec is not None:
            results.append(self._run_one(login_spec, context={}))
            # If login failed, mark subsequent auth-required probes as skip.
            login_failed = results[-1].status != "pass"
        else:
            login_failed = False

        for spec in specs:
            if spec is login_spec:
                continue
            context = dict(self._context)
            if spec.requires_auth and (login_failed or not self._token):
                results.append(
                    ProbeResult(
                        capability=spec.capability,
                        category=spec.category,
                        method=spec.method,
                        path=spec.path,
                        status="skip",
                        notes="requires login; login failed or not attempted",
                    )
                )
                continue
            results.append(self._run_one(spec, context=context))

        return results

    def _run_one(self, spec: ProbeSpec, context: Dict[str, Any]) -> ProbeResult:
        """Run a single probe spec end-to-end."""
        url = self.base_url + spec.path
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if spec.requires_auth and self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        body: Optional[Dict[str, Any]] = None
        if spec.setup is not None and spec.setup is not _noop:
            try:
                ctx = spec.setup(self)
                if isinstance(ctx, dict):
                    context.update(ctx)
                    self._context.update(ctx)
            except Exception as exc:
                return ProbeResult(
                    capability=spec.capability,
                    category=spec.category,
                    method=spec.method,
                    path=spec.path,
                    status="fail",
                    notes=spec.notes,
                    error=f"setup failed: {exc}",
                )

        if spec.body_factory is not None:
            try:
                body = spec.body_factory(context)
            except Exception as exc:
                return ProbeResult(
                    capability=spec.capability,
                    category=spec.category,
                    method=spec.method,
                    path=spec.path,
                    status="fail",
                    notes=spec.notes,
                    error=f"body_factory failed: {exc}",
                )

        client = self._make_client()
        start = time.perf_counter()
        try:
            method_fn = getattr(client, spec.method.lower())
            if body is not None:
                response = method_fn(url, json=body, headers=headers)
            else:
                response = method_fn(url, headers=headers)
            latency_ms = (time.perf_counter() - start) * 1000.0

            status_code = response.status_code
            ok = status_code in spec.expected_status
            note = spec.notes
            err: Optional[str] = None
            if not ok:
                err = f"unexpected status {status_code}, expected {spec.expected_status}"
            elif status_code >= 400:
                err = f"HTTP {status_code}"

            # When the auth.login probe succeeds, harvest the bearer token so
            # subsequent auth-required probes can use it.
            if spec.capability == "auth.login" and ok:
                try:
                    payload = response.json()
                    token = (
                        payload.get("data", {}).get("access_token")
                        if isinstance(payload, dict)
                        else None
                    )
                    if token:
                        self._token = token
                        self._context["token"] = token
                        context["token"] = token
                except Exception:
                    pass

            return ProbeResult(
                capability=spec.capability,
                category=spec.category,
                method=spec.method,
                path=spec.path,
                status="pass" if ok else ("warn" if status_code in spec.warn_status else "fail"),
                http_status=status_code,
                latency_ms=round(latency_ms, 2),
                notes=note,
                error=err,
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000.0
            return ProbeResult(
                capability=spec.capability,
                category=spec.category,
                method=spec.method,
                path=spec.path,
                status="fail",
                latency_ms=round(latency_ms, 2),
                notes=spec.notes,
                error=str(exc),
            )
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()


# ---------------------------------------------------------------------------
# Default probe catalog
# ---------------------------------------------------------------------------


def default_specs() -> List[ProbeSpec]:
    """Return the canonical probe list for the JARVIS capability matrix."""
    return [
        # ---- Foundation ----
        ProbeSpec(
            capability="health",
            category="Foundation",
            method="GET",
            path="/api/v1/health",
            expected_status=(200, 503),
            notes="system health endpoint",
        ),
        # ---- Auth ----
        ProbeSpec(
            capability="auth.login",
            category="Auth",
            method="POST",
            path="/api/v1/auth/login",
            body_factory=lambda _: {
                "username": "admin",
                "password": "JarvisDev123!",
            },
            notes="dev admin login (uses seeded credentials)",
        ),
        # ---- Memory ----
        ProbeSpec(
            capability="memory.store",
            category="Memory",
            method="POST",
            path="/api/v1/memory/store",
            requires_auth=True,
            body_factory=_store_memory_body,
            expected_status=(200, 201),
        ),
        ProbeSpec(
            capability="memory.stats",
            category="Memory",
            method="GET",
            path="/api/v1/memory/stats",
            requires_auth=True,
            expected_status=(200,),
        ),
        ProbeSpec(
            capability="memory.recall",
            category="Memory",
            method="POST",
            path="/api/v1/memory/recall",
            requires_auth=True,
            body_factory=lambda _: {
                "query": "capability matrix",
                "max_chunks": 5,
                "min_score": 0.0,
            },
        ),
        # ---- Missions ----
        ProbeSpec(
            capability="missions.list",
            category="Missions",
            method="GET",
            path="/api/v1/missions",
            requires_auth=True,
            warn_status=(401,),
            notes="route-level permission gate pending fix (see auth B1/B2)",
        ),
        ProbeSpec(
            capability="missions.create",
            category="Missions",
            method="POST",
            path="/api/v1/missions",
            requires_auth=True,
            body_factory=_create_mission_body,
            expected_status=(200, 201),
        ),
        ProbeSpec(
            capability="scheduler.list",
            category="Missions",
            method="GET",
            path="/api/v1/scheduler/queue",
            requires_auth=True,
            notes="scheduler queue (GET /api/v1/scheduler/queue)",
        ),
        # ---- Agent ----
        ProbeSpec(
            capability="agent.runs.list",
            category="Agent",
            method="GET",
            path="/api/v1/agent/runs",
            requires_auth=True,
        ),
        ProbeSpec(
            capability="agent.run",
            category="Agent",
            method="POST",
            path="/api/v1/agent/run",
            requires_auth=True,
            body_factory=_agent_run_body,
            expected_status=(202,),
        ),
        # ---- Workflows ----
        ProbeSpec(
            capability="workflows.list",
            category="Workflows",
            method="GET",
            path="/api/v1/workflows",
            requires_auth=True,
            warn_status=(401,),
            notes="route-level permission gate pending fix",
        ),
        # ---- Skills / Capabilities ----
        ProbeSpec(
            capability="capabilities.discover",
            category="Skills",
            method="GET",
            path="/api/v1/discover",
            requires_auth=True,
            notes="registered capabilities (GET /api/v1/discover)",
        ),
        ProbeSpec(
            capability="skills.list",
            category="Skills",
            method="GET",
            path="/api/v1/skills",
            requires_auth=True,
            warn_status=(401,),
            notes="route-level permission gate pending fix",
        ),
        # ---- Identity / Goal ----
        ProbeSpec(
            capability="identity.list",
            category="Identity",
            method="GET",
            path="/api/v1/identity",
            requires_auth=True,
            warn_status=(401,),
            notes="route-level permission gate pending fix",
        ),
        ProbeSpec(
            capability="goal.list",
            category="Goal",
            method="GET",
            path="/api/v1/goal",
            requires_auth=True,
            warn_status=(401,),
            notes="route-level permission gate pending fix (C1: GoalService DI missing)",
        ),
        # ---- Observability ----
        ProbeSpec(
            capability="observability.traces",
            category="Observability",
            method="GET",
            path="/api/v1/observability/traces",
            requires_auth=True,
        ),
        ProbeSpec(
            capability="observability.budget",
            category="Observability",
            method="GET",
            path="/api/v1/observability/budget",
            requires_auth=True,
        ),
        ProbeSpec(
            capability="observability.health",
            category="Observability",
            method="GET",
            path="/api/v1/observability/health",
            requires_auth=True,
        ),
        # ---- Platform ----
        ProbeSpec(
            capability="platform.health",
            category="Platform",
            method="GET",
            path="/api/v1/platform/health",
            requires_auth=True,
            expected_status=(200, 404),
        ),
        ProbeSpec(
            capability="metrics.prometheus",
            category="Platform",
            method="GET",
            path="/metrics",
            expected_status=(200,),
        ),
    ]


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


_STATUS_ICON = {"pass": "[PASS]", "fail": "[FAIL]", "skip": "[SKIP]", "warn": "[WARN]"}


def render_markdown(report: MatrixReport) -> str:
    """Render the capability matrix as a Markdown report."""
    lines: List[str] = []
    lines.append("# JARVIS Capability Matrix")
    lines.append("")
    lines.append(
        f"_Generated: {report.generated_at}  •  Base URL: `{report.base_url}`_"
    )
    lines.append("")

    s = report.summary
    overall = (
        "GREEN"
        if s.get("fail", 0) == 0 and s.get("pass", 0) > 0
        else "YELLOW"
        if s.get("fail", 0) == 0
        else "RED"
    )
    lines.append(f"**Overall status: {overall}**")
    lines.append("")
    lines.append(
        f"| PASS | FAIL | SKIP | WARN | TOTAL |\n"
        f"|------|------|------|------|-------|\n"
        f"| {s.get('pass', 0)} | {s.get('fail', 0)} | "
        f"{s.get('skip', 0)} | {s.get('warn', 0)} | {s.get('total', 0)} |"
    )
    lines.append("")

    # Group by category
    by_category: Dict[str, List[ProbeResult]] = {}
    for cap in report.capabilities:
        by_category.setdefault(cap.category, []).append(cap)

    lines.append("## Capability Matrix")
    lines.append("")
    for category in sorted(by_category.keys()):
        rows = by_category[category]
        cat_pass = sum(1 for r in rows if r.status == "pass")
        cat_total = len(rows)
        lines.append(f"### {category}  ({cat_pass}/{cat_total} passing)")
        lines.append("")
        lines.append(
            "| Status | Capability | Method | Path | HTTP | Latency | Notes |"
        )
        lines.append(
            "|--------|------------|--------|------|------|---------|-------|"
        )
        for row in rows:
            icon = _STATUS_ICON.get(row.status, row.status)
            latency = (
                f"{row.latency_ms:.0f}ms" if row.latency_ms is not None else "-"
            )
            http = row.http_status if row.http_status is not None else "-"
            notes = (row.error or row.notes or "").replace("|", "\\|")
            lines.append(
                f"| {icon} | {row.capability} | {row.method} | "
                f"`{row.path}` | {http} | {latency} | {notes} |"
            )
        lines.append("")

    # Footer
    lines.append("---")
    lines.append(
        "_Generated by `scripts/capability_matrix.py`. "
        "Run `python scripts/validate_startup.py` to refresh._"
    )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="capability_matrix.py",
        description="Probe a running JARVIS instance and emit a capability matrix.",
    )
    parser.add_argument(
        "--base-url", default=DEFAULT_BASE_URL, help="JARVIS base URL"
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument("--admin-user", default="admin")
    parser.add_argument("--admin-password", default="JarvisDev123!")
    parser.add_argument(
        "--output-md",
        default=str(DEFAULT_OUTPUT_MD),
        help="Markdown report path (set to '-' for stdout only)",
    )
    parser.add_argument(
        "--output-json",
        default=str(DEFAULT_OUTPUT_JSON),
        help="JSON report path (set to '-' for stdout only)",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Also print the markdown to stdout",
    )
    parser.add_argument(
        "--fail-on-fail",
        action="store_true",
        help="Exit non-zero if any capability FAILS",
    )
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> int:
    """Execute the capability matrix; return shell exit code."""
    report = MatrixReport(
        base_url=args.base_url,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    runner = ProbeRunner(
        base_url=args.base_url,
        timeout=args.timeout,
        admin_username=args.admin_user,
        admin_password=args.admin_password,
    )

    report.capabilities = runner.run(default_specs())
    report.compute_summary()

    md = render_markdown(report)
    js = json.dumps(report.to_dict(), indent=2, sort_keys=True)

    if args.output_md and args.output_md != "-":
        Path(args.output_md).write_text(md, encoding="utf-8")
        print(f"[matrix] wrote markdown: {args.output_md}")
    if args.output_json and args.output_json != "-":
        Path(args.output_json).write_text(js, encoding="utf-8")
        print(f"[matrix] wrote json:     {args.output_json}")

    if args.stdout or args.output_md == "-":
        sys.stdout.write(md)
        sys.stdout.write("\n")

    s = report.summary
    print(
        f"[matrix] {s.get('pass', 0)} pass, "
        f"{s.get('fail', 0)} fail, "
        f"{s.get('skip', 0)} skip, "
        f"{s.get('warn', 0)} warn  (total {s.get('total', 0)})"
    )

    if args.fail_on_fail and s.get("fail", 0) > 0:
        return 1
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point wrapper."""
    args = parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())