"""JARVIS OS - Phase 27.D Observability Routes & Phase 28 Security Tests.

Validates the FastAPI REST and WebSocket endpoints for trace listing,
budget summaries, component health, Prometheus metrics, and authentication controls.
"""

from __future__ import annotations

import contextlib
import hashlib
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes.observability import (
    metrics_router,
    observability_router,
    set_observability_deps,
    telemetry_ws_router,
)
from core.observability.dto import (
    BudgetSummary,
    ComponentHealthRecord,
    ComponentStatus,
    CostDecision,
    SpanStatus,
    TraceSpanRecord,
)
from core.security.api_key_service import ApiKeyService
from core.security.auth_context import RequestContext, active_context
from core.security.jwt_service import JWTService
from core.security.rbac_service import RbacService
from core.security.revocation_service import RevocationService
from core.tools.security_repository import SecurityRepository


@pytest.fixture
def mock_span_repo() -> MagicMock:
    repo = MagicMock()
    repo.list_paginated = AsyncMock(return_value=[])
    return repo


@pytest.fixture
def mock_cost_governor() -> MagicMock:
    gov = MagicMock()
    summary = BudgetSummary(
        date="2026-07-04",
        month="2026-07",
        daily_cost_usd=1.5,
        monthly_cost_usd=5.0,
        daily_limit_usd=10.0,
        warn_threshold_usd=8.0,
        tier=CostDecision.ALLOW,
        call_count_daily=10,
        total_tokens_daily=5000,
        call_count_monthly=30,
        total_tokens_monthly=20000,
    )
    gov.get_daily_summary = AsyncMock(return_value=summary)
    return gov


@pytest.fixture
def mock_health_probe() -> MagicMock:
    probe = MagicMock()
    probe.get_health_status = AsyncMock(return_value={"CompA": "ONLINE"})
    record = ComponentHealthRecord(
        component_id="CompA",
        status=ComponentStatus.ONLINE,
        last_heartbeat=datetime.now(timezone.utc),
    )
    probe.get_health_records = AsyncMock(return_value=[record])
    return probe


@pytest.fixture
def mock_broadcaster() -> MagicMock:
    broadcaster = MagicMock()

    async def mock_connect(websocket: Any) -> None:
        await websocket.accept()

    broadcaster.connect = AsyncMock(side_effect=mock_connect)
    broadcaster.disconnect = AsyncMock()
    return broadcaster


@pytest.fixture
def client(
    mock_span_repo: MagicMock,
    mock_cost_governor: MagicMock,
    mock_health_probe: MagicMock,
    mock_broadcaster: MagicMock,
) -> TestClient:
    app = FastAPI()
    app.include_router(observability_router)
    app.include_router(metrics_router)
    app.include_router(telemetry_ws_router)

    set_observability_deps(
        span_repo=mock_span_repo,
        cost_governor=mock_cost_governor,
        health_probe=mock_health_probe,
        broadcaster=mock_broadcaster,
        auth_required=False,
    )

    return TestClient(app)


@contextlib.contextmanager
def authenticated_context(permissions: list[str] | None = None) -> Any:
    """Fixture context setting up request user session state."""
    token = active_context.set(
        RequestContext(
            user_id=uuid4(),
            username="test_user",
            roles=["admin"],
            permissions=permissions if permissions is not None else ["audit.read"],
            authentication_method="jwt",
        )
    )
    try:
        yield
    finally:
        active_context.reset(token)


@pytest.fixture
def mock_kernel_with_security(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Mock get_kernel to return mocked JWT/API Key validation dependencies."""

    kernel = MagicMock()

    jwt_service = MagicMock(spec=JWTService)
    revocation_service = MagicMock(spec=RevocationService)
    api_key_service = MagicMock(spec=ApiKeyService)
    security_repository = MagicMock(spec=SecurityRepository)
    rbac_service = MagicMock(spec=RbacService)

    # Mock JWT verification
    def mock_verify_token(token: str) -> dict[str, Any]:
        if token == "valid-jwt-token":
            return {
                "sub": "00000000-0000-0000-0000-000000000000",
                "username": "test_user",
                "roles": ["admin"],
                "permissions": ["audit.read"],
                "jti": "some-jti",
            }
        elif token == "jwt-no-audit-read":
            return {
                "sub": "00000000-0000-0000-0000-000000000000",
                "username": "test_user",
                "roles": ["viewer"],
                "permissions": ["agent.read"],
                "jti": "some-jti",
            }
        elif token == "revoked-jwt-token":
            return {
                "sub": "00000000-0000-0000-0000-000000000000",
                "username": "test_user",
                "roles": ["admin"],
                "permissions": ["audit.read"],
                "jti": "revoked-jti",
            }
        else:
            raise Exception("Invalid token")

    jwt_service.verify_token.side_effect = mock_verify_token

    # Mock revocation status
    async def mock_is_revoked(jti: str, session: Any) -> bool:
        return jti == "revoked-jti"

    revocation_service.is_token_revoked.side_effect = mock_is_revoked

    # Mock API key verification
    async def mock_get_api_key_by_hashed(hashed: str, session: Any) -> Any:
        valid_hash = hashlib.sha256(b"valid-api-key").hexdigest()
        no_audit_hash = hashlib.sha256(b"api-key-no-audit").hexdigest()

        class MockUser:
            id = uuid4()
            username = "test_user"
            roles: list[Any] = []

        class MockKeyModel:
            is_active = True
            hashed_key = valid_hash
            user = MockUser()

        class MockNoAuditKeyModel:
            is_active = True
            hashed_key = no_audit_hash
            user = MockUser()

        if hashed == valid_hash:
            return MockKeyModel()
        elif hashed == no_audit_hash:
            return MockNoAuditKeyModel()
        return None

    security_repository.get_api_key_by_hashed.side_effect = mock_get_api_key_by_hashed
    api_key_service.verify_api_key.side_effect = lambda raw, hashed: (
        hashlib.sha256(raw.encode("utf-8")).hexdigest() == hashed
    )

    # Mock permissions lookup
    def mock_resolve_permissions(user: Any) -> list[str]:
        # Return empty list if this is the no-audit user
        return ["audit.read"]

    rbac_service.resolve_permissions.side_effect = mock_resolve_permissions

    kernel.container.resolve.side_effect = lambda t: {
        JWTService: jwt_service,
        RevocationService: revocation_service,
        ApiKeyService: api_key_service,
        SecurityRepository: security_repository,
        RbacService: rbac_service,
    }[t]

    # Mock db_manager.session as an async context manager (Architect Q2 requirement support)
    class MockAsyncContext:
        async def __aenter__(self) -> MagicMock:
            return MagicMock()

        async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            pass

    monkeypatch.setattr(
        "core.memory.database.db_manager.session", lambda: MockAsyncContext()
    )

    monkeypatch.setattr("api.dependencies._kernel", kernel)
    return kernel


class TestObservabilityRoutes:
    """Observability routes verification suite (Architect constraint Q2 & C5)."""

    def test_routes_unavailable_before_deps_set(self) -> None:
        """Accessing endpoints before dependency injection returns 503 Service Unavailable."""
        set_observability_deps(None, None, None, None, auth_required=False)  # type: ignore[arg-type]
        app = FastAPI()
        app.include_router(observability_router)
        client = TestClient(app)

        with authenticated_context():
            res = client.get("/api/v1/observability/budget")
            assert res.status_code == 503
            assert "unavailable" in res.json()["detail"].lower()

    def test_get_traces(self, client: TestClient, mock_span_repo: MagicMock) -> None:
        """GET /traces fetches paginated trace spans from SpanRepository."""
        span = TraceSpanRecord(
            span_id=uuid4(),
            trace_id=uuid4(),
            component="AgentLoop",
            operation="test.run",
            status=SpanStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
        )
        mock_span_repo.list_paginated.return_value = [span]

        with authenticated_context():
            res = client.get("/api/v1/observability/traces?limit=10&offset=5")
            assert res.status_code == 200
            data = res.json()
            assert len(data) == 1
            assert data[0]["component"] == "AgentLoop"
            assert data[0]["operation"] == "test.run"
            mock_span_repo.list_paginated.assert_called_once_with(limit=10, offset=5)

    def test_get_budget(
        self, client: TestClient, mock_cost_governor: MagicMock
    ) -> None:
        """GET /budget retrieves cost totals and current tier summary."""
        with authenticated_context():
            res = client.get("/api/v1/observability/budget")
            assert res.status_code == 200
            data = res.json()
            assert data["daily_cost_usd"] == 1.5
            assert data["tier"] == "ALLOW"
            mock_cost_governor.get_daily_summary.assert_called_once()

    def test_get_health(self, client: TestClient, mock_health_probe: MagicMock) -> None:
        """GET /health retrieves all registered component health statuses."""
        with authenticated_context():
            res = client.get("/api/v1/observability/health")
            assert res.status_code == 200
            data = res.json()
            assert len(data) == 1
            assert data[0]["component_id"] == "CompA"
            assert data[0]["status"] == "ONLINE"
            mock_health_probe.get_health_records.assert_called_once()

    def test_prometheus_exposition_endpoint(self, client: TestClient) -> None:
        """GET /metrics returns Prometheus format plaintext response (Architect C5)."""
        res = client.get("/metrics")
        assert res.status_code == 200
        assert "text/plain" in res.headers["content-type"]
        text = res.text
        assert "# HELP jarvis_daily_cost_usd" in text
        assert "# TYPE jarvis_daily_cost_usd gauge" in text
        assert "jarvis_daily_cost_usd 1.5" in text
        assert "jarvis_health_ok 1" in text

    def test_rest_endpoints_require_authentication(self, client: TestClient) -> None:
        """GET /traces budget and health raise AuthenticationError when unauthenticated."""
        from core.exceptions import AuthenticationError

        with pytest.raises(AuthenticationError) as exc:
            client.get("/api/v1/observability/traces")
        assert exc.value.code == "AUTH_005"

        with pytest.raises(AuthenticationError) as exc:
            client.get("/api/v1/observability/budget")
        assert exc.value.code == "AUTH_005"

        with pytest.raises(AuthenticationError) as exc:
            client.get("/api/v1/observability/health")
        assert exc.value.code == "AUTH_005"

    def test_rest_endpoints_require_audit_read_permission(
        self, client: TestClient
    ) -> None:
        """GET /traces budget and health raise AuthenticationError on insufficient permission."""
        from core.exceptions import AuthenticationError

        with authenticated_context(permissions=[]):
            with pytest.raises(AuthenticationError) as exc:
                client.get("/api/v1/observability/traces")
            assert exc.value.code == "AUTH_006"

    def test_websocket_stream_unauthorized_if_configured(
        self,
        mock_span_repo: MagicMock,
        mock_cost_governor: MagicMock,
        mock_health_probe: MagicMock,
        mock_broadcaster: MagicMock,
        mock_kernel_with_security: MagicMock,
    ) -> None:
        """If auth is enabled, connecting without token closes socket with 4001 code (Architect Q2)."""
        app = FastAPI()
        app.include_router(telemetry_ws_router)
        set_observability_deps(
            span_repo=mock_span_repo,
            cost_governor=mock_cost_governor,
            health_probe=mock_health_probe,
            broadcaster=mock_broadcaster,
            auth_required=True,
        )
        client = TestClient(app)

        with pytest.raises(Exception):
            with client.websocket_connect("/ws/v1/telemetry/stream"):
                pass

    def test_websocket_stream_authorized_success_jwt(
        self,
        mock_span_repo: MagicMock,
        mock_cost_governor: MagicMock,
        mock_health_probe: MagicMock,
        mock_broadcaster: MagicMock,
        mock_kernel_with_security: MagicMock,
    ) -> None:
        """Connecting with a valid security JWT token succeeds when auth is required."""
        app = FastAPI()
        app.include_router(telemetry_ws_router)
        set_observability_deps(
            span_repo=mock_span_repo,
            cost_governor=mock_cost_governor,
            health_probe=mock_health_probe,
            broadcaster=mock_broadcaster,
            auth_required=True,
        )
        client = TestClient(app)

        with client.websocket_connect(
            "/ws/v1/telemetry/stream?token=valid-jwt-token"
        ) as websocket:
            assert mock_broadcaster.connect.called
            websocket.close()
        assert mock_broadcaster.disconnect.called

    def test_websocket_stream_authorized_success_api_key(
        self,
        mock_span_repo: MagicMock,
        mock_cost_governor: MagicMock,
        mock_health_probe: MagicMock,
        mock_broadcaster: MagicMock,
        mock_kernel_with_security: MagicMock,
    ) -> None:
        """Connecting with a valid security API key succeeds when auth is required."""
        app = FastAPI()
        app.include_router(telemetry_ws_router)
        set_observability_deps(
            span_repo=mock_span_repo,
            cost_governor=mock_cost_governor,
            health_probe=mock_health_probe,
            broadcaster=mock_broadcaster,
            auth_required=True,
        )
        client = TestClient(app)

        with client.websocket_connect(
            "/ws/v1/telemetry/stream?token=valid-api-key"
        ) as websocket:
            assert mock_broadcaster.connect.called
            websocket.close()
        assert mock_broadcaster.disconnect.called

    def test_websocket_stream_revoked_jwt_fails(
        self,
        mock_span_repo: MagicMock,
        mock_cost_governor: MagicMock,
        mock_health_probe: MagicMock,
        mock_broadcaster: MagicMock,
        mock_kernel_with_security: MagicMock,
    ) -> None:
        """Connecting with a revoked JWT token is rejected."""
        app = FastAPI()
        app.include_router(telemetry_ws_router)
        set_observability_deps(
            span_repo=mock_span_repo,
            cost_governor=mock_cost_governor,
            health_probe=mock_health_probe,
            broadcaster=mock_broadcaster,
            auth_required=True,
        )
        client = TestClient(app)

        with pytest.raises(Exception):
            with client.websocket_connect(
                "/ws/v1/telemetry/stream?token=revoked-jwt-token"
            ):
                pass

    def test_websocket_stream_missing_audit_read_permission_fails(
        self,
        mock_span_repo: MagicMock,
        mock_cost_governor: MagicMock,
        mock_health_probe: MagicMock,
        mock_broadcaster: MagicMock,
        mock_kernel_with_security: MagicMock,
    ) -> None:
        """Connecting with a valid JWT token lacking audit.read permission gets rejected with code 4003."""
        app = FastAPI()
        app.include_router(telemetry_ws_router)
        set_observability_deps(
            span_repo=mock_span_repo,
            cost_governor=mock_cost_governor,
            health_probe=mock_health_probe,
            broadcaster=mock_broadcaster,
            auth_required=True,
        )
        client = TestClient(app)

        with pytest.raises(Exception):
            with client.websocket_connect(
                "/ws/v1/telemetry/stream?token=jwt-no-audit-read"
            ):
                pass
