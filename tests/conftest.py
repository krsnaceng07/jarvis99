"""Shared pytest fixtures for JARVIS OS integration tests."""

from uuid import uuid4

import pytest

from core.security.auth_context import RequestContext
from core.security.configuration_service import ConfigurationService
from core.security.jwt_service import JWTService

ALL_TEST_PERMISSIONS = [
    "agent.execute",
    "agent.read",
    "workflow.execute",
    "workflow.read",
    "audit.read",
]

_GATEWAY_TEST_MODULES = frozenset(
    {
        "test_api_security",
        "test_persistent_execution",
        "test_api_gateway",
    }
)


def _is_gateway_test(request: pytest.FixtureRequest) -> bool:
    module_name = request.module.__name__.rsplit(".", 1)[-1]
    return module_name in _GATEWAY_TEST_MODULES


@pytest.fixture(autouse=True)
def gateway_sqlite_database(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Route gateway/kernel boots to in-memory SQLite for hermetic API tests."""
    if not _is_gateway_test(request):
        return
    monkeypatch.setenv("JARVIS_DATABASE__HOST", "sqlite")
    monkeypatch.setenv("JARVIS_DATABASE__NAME", ":memory:")
    monkeypatch.setenv("JARVIS_SYSTEM__ENVIRONMENT", "development")


@pytest.fixture(autouse=True)
def reset_kernel_singleton(request: pytest.FixtureRequest) -> None:
    """Clear the API-layer kernel singleton between gateway tests."""
    if not _is_gateway_test(request):
        yield
        return
    import api.dependencies as deps

    deps._kernel = None
    yield
    deps._kernel = None


@pytest.fixture
def mock_request_context() -> RequestContext:
    """Minimal authenticated context for direct route handler unit tests."""
    return RequestContext(
        user_id=uuid4(),
        username="test-user",
        roles=["admin"],
        permissions=ALL_TEST_PERMISSIONS,
        authentication_method="jwt",
    )


@pytest.fixture
def auth_headers() -> dict[str, str]:
    """Bearer JWT using the same defaults as the kernel ConfigurationService."""
    config = ConfigurationService()
    service = JWTService(config)
    token = service.sign_token(
        user_id=str(uuid4()),
        username="integration-test-user",
        roles=["admin"],
        permissions=ALL_TEST_PERMISSIONS,
        jti=str(uuid4()),
    )
    return {"Authorization": f"Bearer {token}"}
