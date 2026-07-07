"""
PHASE: 42
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/104_PHASE_42_IDENTITY_ENGINE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/21be4144-6686-48ed-8e46-74ce7e189cd4/implementation_plan.md

AUTHORITATIVE:
    NO

Tests: Identity Engine (Phase 42)
Covers: AgentIdentity DTO, IdentityRepository CRUD, IdentityService business logic
        (single-active invariant, cache, fallback, side-effects, events),
        BrainKernel integration, API route handlers (mocked service layer).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_identity(**kwargs: Any):
    """Create a test AgentIdentity with sensible defaults."""
    from core.reasoning.identity import AgentIdentity

    defaults: Dict[str, Any] = {
        "name": "Test Identity",
        "role": "developer",
        "system_prompt": "You are a developer assistant.",
        "personality": "focused",
        "communication_style": "technical",
        "allowed_capabilities": ["code", "debug"],
        "default_model": "gemini-pro",
        "memory_scope": "project",
        "permission_profile": "developer",
        "metadata": {"language": "python"},
        "is_active": False,
    }
    defaults.update(kwargs)
    return AgentIdentity(**defaults)


def _make_identity_model(**kwargs: Any):
    """Create a test AgentIdentityModel ORM instance."""
    from core.memory.models import AgentIdentityModel

    defaults: Dict[str, Any] = {
        "id": uuid4(),
        "name": "Test Identity",
        "role": "developer",
        "system_prompt": "You are a developer assistant.",
        "personality": "focused",
        "communication_style": "technical",
        "allowed_capabilities": ["code", "debug"],
        "default_model": "gemini-pro",
        "memory_scope": "project",
        "permission_profile": "developer",
        "metadata_": {"language": "python"},
        "is_active": False,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    return AgentIdentityModel(**defaults)


# ===========================================================================
# 1. AgentIdentity DTO tests
# ===========================================================================


class TestAgentIdentityDTO:
    """Unit tests for the AgentIdentity Pydantic model."""

    def test_create_minimal_identity(self) -> None:
        """AgentIdentity can be created with only required fields."""
        from core.reasoning.identity import AgentIdentity

        identity = AgentIdentity(
            name="Minimal",
            role="assistant",
            system_prompt="Help the user.",
        )
        assert identity.name == "Minimal"
        assert identity.role == "assistant"
        assert identity.is_active is False
        assert identity.allowed_capabilities == []
        assert identity.metadata == {}

    def test_create_full_identity(self) -> None:
        """AgentIdentity stores all fields correctly."""
        identity = _make_identity(is_active=True)
        assert identity.name == "Test Identity"
        assert identity.role == "developer"
        assert identity.is_active is True
        assert identity.allowed_capabilities == ["code", "debug"]
        assert identity.metadata["language"] == "python"

    def test_identity_has_auto_uuid(self) -> None:
        """AgentIdentity auto-generates a UUID id."""
        from core.reasoning.identity import AgentIdentity

        a = AgentIdentity(name="A", role="r", system_prompt="s")
        b = AgentIdentity(name="B", role="r", system_prompt="s")
        assert a.id != b.id
        assert isinstance(a.id, UUID)

    def test_identity_timestamps(self) -> None:
        """created_at and updated_at are timezone-aware datetimes."""
        identity = _make_identity()
        assert identity.created_at.tzinfo is not None
        assert identity.updated_at.tzinfo is not None

    def test_identity_missing_required_fields_raises(self) -> None:
        """Missing required fields raise ValidationError."""
        from core.reasoning.identity import AgentIdentity

        with pytest.raises(ValidationError):
            AgentIdentity(role="developer", system_prompt="s")  # missing name

    def test_default_identity_constant(self) -> None:
        """DEFAULT_IDENTITY is a valid AgentIdentity with correct defaults."""
        from core.reasoning.identity import DEFAULT_IDENTITY

        assert DEFAULT_IDENTITY.name == "JARVIS Default"
        assert DEFAULT_IDENTITY.is_active is True
        assert DEFAULT_IDENTITY.id == UUID("00000000-0000-0000-0000-000000000000")


# ===========================================================================
# 2. IdentityRepository unit tests (in-memory with mocked session)
# ===========================================================================


class TestIdentityRepository:
    """Unit tests for IdentityRepository using mock AsyncSession."""

    @pytest.fixture
    def repo(self):
        from core.reasoning.identity_repository import IdentityRepository
        return IdentityRepository()

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.delete = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_save_identity_adds_to_session(self, repo, mock_session) -> None:
        """save_identity adds the model and flushes."""
        model = _make_identity_model()
        await repo.save_identity(model, mock_session)
        mock_session.add.assert_called_once_with(model)
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_identity_returns_model(self, repo, mock_session) -> None:
        """get_identity executes the correct query."""
        model = _make_identity_model()
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = model
        mock_session.execute = AsyncMock(return_value=result_mock)

        found = await repo.get_identity(model.id, mock_session)
        assert found is model
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_identity_not_found_returns_none(self, repo, mock_session) -> None:
        """get_identity returns None when not found."""
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=result_mock)

        found = await repo.get_identity(uuid4(), mock_session)
        assert found is None

    @pytest.mark.asyncio
    async def test_get_active_identity(self, repo, mock_session) -> None:
        """get_active_identity returns model with is_active=True."""
        model = _make_identity_model(is_active=True)
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = model
        mock_session.execute = AsyncMock(return_value=result_mock)

        found = await repo.get_active_identity(mock_session)
        assert found is model
        assert found.is_active is True

    @pytest.mark.asyncio
    async def test_activate_identity_executes_two_updates(self, repo, mock_session) -> None:
        """activate_identity runs deactivate-all then activate-one statements."""
        mock_session.execute = AsyncMock()
        mock_session.flush = AsyncMock()

        target_id = uuid4()
        await repo.activate_identity(target_id, mock_session)

        assert mock_session.execute.await_count == 2
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_list_identities_returns_all(self, repo, mock_session) -> None:
        """list_identities returns all rows."""
        models = [_make_identity_model(), _make_identity_model()]
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = models
        mock_session.execute = AsyncMock(return_value=result_mock)

        result = await repo.list_identities(mock_session)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_delete_identity_found(self, repo, mock_session) -> None:
        """delete_identity returns True when record exists."""
        model = _make_identity_model()
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = model
        mock_session.execute = AsyncMock(return_value=result_mock)
        mock_session.delete = AsyncMock()
        mock_session.flush = AsyncMock()

        deleted = await repo.delete_identity(model.id, mock_session)
        assert deleted is True
        mock_session.delete.assert_awaited_once_with(model)

    @pytest.mark.asyncio
    async def test_delete_identity_not_found(self, repo, mock_session) -> None:
        """delete_identity returns False when record does not exist."""
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=result_mock)

        deleted = await repo.delete_identity(uuid4(), mock_session)
        assert deleted is False


# ===========================================================================
# 3. IdentityService unit tests (mocked repo + event bus)
# ===========================================================================


class TestIdentityService:
    """Unit tests for IdentityService business logic."""

    @pytest.fixture
    def mock_repo(self):
        return AsyncMock()

    @pytest.fixture
    def mock_event_bus(self):
        bus = AsyncMock()
        bus.publish = AsyncMock()
        return bus

    @pytest.fixture
    def service(self, mock_repo, mock_event_bus):
        from core.reasoning.identity import IdentityService
        return IdentityService(repository=mock_repo, event_bus=mock_event_bus)

    # -----------------------------------------------------------------------
    # Cache behaviour
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_active_identity_uses_cache(self, service, mock_repo) -> None:
        """Second call returns cached identity, not a DB call."""
        identity = _make_identity(is_active=True)
        service._cached_active_identity = identity

        result = await service.get_active_identity()
        assert result is identity
        mock_repo.get_active_identity.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_active_identity_fallback(self, service, mock_repo) -> None:
        """Falls back to DEFAULT_IDENTITY when DB returns None."""
        from core.reasoning.identity import DEFAULT_IDENTITY

        mock_repo.get_active_identity = AsyncMock(return_value=None)
        with patch("core.memory.database.db_manager") as mock_db:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_db.session.return_value = mock_sess
            mock_repo.get_active_identity = AsyncMock(return_value=None)

            result = await service.get_active_identity()
        assert result.id == DEFAULT_IDENTITY.id

    # -----------------------------------------------------------------------
    # Single-active invariant
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_activate_identity_updates_cache(self, service, mock_repo) -> None:
        """activate_identity sets _cached_active_identity to the activated record."""
        identity = _make_identity(is_active=True)
        model = _make_identity_model(
            id=identity.id,
            name=identity.name,
            role=identity.role,
            system_prompt=identity.system_prompt,
            is_active=True,
        )

        with patch("core.memory.database.db_manager") as mock_db:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_sess.commit = AsyncMock()
            mock_db.session.return_value = mock_sess
            mock_repo.get_identity = AsyncMock(return_value=model)
            mock_repo.activate_identity = AsyncMock()

            await service.activate_identity(identity.id)

        assert service._cached_active_identity is not None
        assert service._cached_active_identity.id == identity.id

    @pytest.mark.asyncio
    async def test_activate_identity_not_found_raises(self, service, mock_repo) -> None:
        """activate_identity raises ValueError for unknown ID."""
        with patch("core.memory.database.db_manager") as mock_db:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_db.session.return_value = mock_sess
            mock_repo.get_identity = AsyncMock(return_value=None)

            with pytest.raises(ValueError, match="not found"):
                await service.activate_identity(uuid4())

    # -----------------------------------------------------------------------
    # Event publishing
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_identity_publishes_event(self, service, mock_repo, mock_event_bus) -> None:
        """create_identity publishes 'identity.created' event."""
        identity = _make_identity()

        with patch("core.memory.database.db_manager") as mock_db:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_sess.commit = AsyncMock()
            mock_db.session.return_value = mock_sess
            mock_repo.save_identity = AsyncMock()

            await service.create_identity(identity)

        mock_event_bus.publish.assert_awaited_once()
        call_args = mock_event_bus.publish.call_args
        assert call_args[0][0] == "identity.created"

    @pytest.mark.asyncio
    async def test_activate_identity_publishes_event(self, service, mock_repo, mock_event_bus) -> None:
        """activate_identity publishes 'identity.activated' event."""
        identity = _make_identity()
        model = _make_identity_model(
            id=identity.id,
            name=identity.name,
            role=identity.role,
            system_prompt=identity.system_prompt,
        )

        with patch("core.memory.database.db_manager") as mock_db:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_sess.commit = AsyncMock()
            mock_db.session.return_value = mock_sess
            mock_repo.get_identity = AsyncMock(return_value=model)
            mock_repo.activate_identity = AsyncMock()

            await service.activate_identity(identity.id)

        mock_event_bus.publish.assert_awaited_once()
        call_args = mock_event_bus.publish.call_args
        assert call_args[0][0] == "identity.activated"

    # -----------------------------------------------------------------------
    # Side effects: working memory flush
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_side_effects_clear_working_memory(self, service, mock_repo) -> None:
        """_apply_side_effects calls working_memory.clear() when set."""
        working_memory = MagicMock()
        working_memory.clear = MagicMock()
        service.working_memory = working_memory

        identity = _make_identity(is_active=True)
        await service._apply_side_effects(identity)
        working_memory.clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_side_effects_update_brain_context(self, service) -> None:
        """_apply_side_effects updates brain_context when set."""
        brain_context = MagicMock()
        brain_context.set = MagicMock()
        service.brain_context = brain_context

        identity = _make_identity()
        await service._apply_side_effects(identity)
        brain_context.set.assert_called_once_with(
            "active_identity", identity.model_dump(mode="json")
        )

    # -----------------------------------------------------------------------
    # Cache invalidation
    # -----------------------------------------------------------------------

    def test_invalidate_cache(self, service) -> None:
        """invalidate_cache clears _cached_active_identity."""
        service._cached_active_identity = _make_identity()
        service.invalidate_cache()
        assert service._cached_active_identity is None

    # -----------------------------------------------------------------------
    # Delete + fallback to default
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_delete_active_identity_clears_cache(self, service, mock_repo) -> None:
        """Deleting the active identity clears cache and applies default side-effects."""
        identity = _make_identity(is_active=True)
        service._cached_active_identity = identity

        with patch("core.memory.database.db_manager") as mock_db:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_sess.commit = AsyncMock()
            mock_db.session.return_value = mock_sess
            mock_repo.delete_identity = AsyncMock(return_value=True)

            result = await service.delete_identity(identity.id)

        assert result is True
        assert service._cached_active_identity is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_identity_returns_false(self, service, mock_repo) -> None:
        """Deleting non-existent identity returns False."""
        with patch("core.memory.database.db_manager") as mock_db:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_sess.commit = AsyncMock()
            mock_db.session.return_value = mock_sess
            mock_repo.delete_identity = AsyncMock(return_value=False)

            result = await service.delete_identity(uuid4())

        assert result is False

    # -----------------------------------------------------------------------
    # list_identities
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_list_identities_returns_dtos(self, service, mock_repo) -> None:
        """list_identities returns a list of AgentIdentity DTOs."""
        models = [_make_identity_model(), _make_identity_model()]
        with patch("core.memory.database.db_manager") as mock_db:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_db.session.return_value = mock_sess
            mock_repo.list_identities = AsyncMock(return_value=models)

            result = await service.list_identities()

        assert len(result) == 2
        from core.reasoning.identity import AgentIdentity
        for item in result:
            assert isinstance(item, AgentIdentity)


# ===========================================================================
# 4. to_identity_dto mapping test
# ===========================================================================


class TestIdentityDTOMapping:
    """Tests for the to_identity_dto helper."""

    def test_to_identity_dto_maps_all_fields(self) -> None:
        """to_identity_dto correctly maps all AgentIdentityModel fields to AgentIdentity."""
        from core.memory.models import to_identity_dto
        from core.reasoning.identity import AgentIdentity

        model = _make_identity_model(name="Mapped", role="researcher", is_active=True)
        dto = to_identity_dto(model)

        assert isinstance(dto, AgentIdentity)
        assert dto.id == model.id
        assert dto.name == "Mapped"
        assert dto.role == "researcher"
        assert dto.is_active is True
        assert dto.metadata == model.metadata_

    def test_to_identity_dto_optional_fields_none(self) -> None:
        """to_identity_dto handles None optional fields cleanly."""
        from core.memory.models import to_identity_dto

        model = _make_identity_model(
            personality=None,
            communication_style=None,
            default_model=None,
            memory_scope=None,
            permission_profile=None,
        )
        dto = to_identity_dto(model)
        assert dto.personality is None
        assert dto.communication_style is None
        assert dto.default_model is None


# ===========================================================================
# 5. API Route handler tests (mocked IdentityService)
# ===========================================================================


class TestIdentityRoutes:
    """Integration-style tests for API route handlers using mocked service."""

    @pytest.fixture
    def mock_service(self):
        return AsyncMock()

    @pytest.fixture
    def client(self, mock_service):
        """Create a TestClient with overridden dependencies."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from api.dependencies import get_identity_service
        from api.routes.identity import router

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_identity_service] = lambda: mock_service

        return TestClient(app)

    def test_list_identities_empty(self, client, mock_service) -> None:
        """GET /api/v1/identities returns empty list when no identities exist."""
        mock_service.list_identities = AsyncMock(return_value=[])
        response = client.get("/identities")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_identities_returns_data(self, client, mock_service) -> None:
        """GET /api/v1/identities returns serialised identities."""
        identity = _make_identity(name="DevBot")
        mock_service.list_identities = AsyncMock(return_value=[identity])

        response = client.get("/identities")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "DevBot"
        assert data[0]["role"] == "developer"

    def test_create_identity_success(self, client, mock_service) -> None:
        """POST /api/v1/identities creates and returns the new identity."""
        identity = _make_identity(name="ResearchBot", role="researcher")
        mock_service.create_identity = AsyncMock(return_value=identity)

        payload = {
            "name": "ResearchBot",
            "role": "researcher",
            "system_prompt": "You are a research assistant.",
        }
        response = client.post("/identities", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "ResearchBot"

    def test_create_identity_missing_required_field(self, client, mock_service) -> None:
        """POST /api/v1/identities with missing required fields returns 422."""
        response = client.post("/identities", json={"role": "developer"})
        assert response.status_code == 422

    def test_get_active_identity(self, client, mock_service) -> None:
        """GET /api/v1/identities/active returns active identity."""
        identity = _make_identity(is_active=True)
        mock_service.get_active_identity = AsyncMock(return_value=identity)

        response = client.get("/identities/active")
        assert response.status_code == 200
        data = response.json()
        assert data["is_active"] is True

    def test_activate_identity_success(self, client, mock_service) -> None:
        """POST /api/v1/identities/{id}/activate returns activation response."""
        identity = _make_identity(is_active=True)
        mock_service.activate_identity = AsyncMock(return_value=identity)

        response = client.post(f"/identities/{identity.id}/activate")
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "now active" in data["message"]

    def test_activate_identity_not_found(self, client, mock_service) -> None:
        """POST /api/v1/identities/{id}/activate returns 404 for unknown id."""
        mock_service.activate_identity = AsyncMock(
            side_effect=ValueError("Identity with ID x not found.")
        )
        response = client.post(f"/identities/{uuid4()}/activate")
        assert response.status_code == 404

    def test_delete_identity_success(self, client, mock_service) -> None:
        """DELETE /api/v1/identities/{id} returns 204 on success."""
        identity = _make_identity()
        mock_service.delete_identity = AsyncMock(return_value=True)

        response = client.delete(f"/identities/{identity.id}")
        assert response.status_code == 204

    def test_delete_identity_not_found(self, client, mock_service) -> None:
        """DELETE /api/v1/identities/{id} returns 404 for unknown id."""
        mock_service.delete_identity = AsyncMock(return_value=False)

        response = client.delete(f"/identities/{uuid4()}")
        assert response.status_code == 404

    def test_list_identities_service_error(self, client, mock_service) -> None:
        """GET /api/v1/identities returns 500 on unexpected service error."""
        mock_service.list_identities = AsyncMock(side_effect=RuntimeError("DB down"))
        response = client.get("/identities")
        assert response.status_code == 500


# ===========================================================================
# 6. BrainKernel identity integration tests
# ===========================================================================


class TestBrainKernelIdentityIntegration:
    """Verify BrainKernel correctly delegates to IdentityService."""

    @pytest.fixture
    def mock_identity_service(self):
        return AsyncMock()

    @pytest.fixture
    def brain_kernel(self, mock_identity_service):
        """Construct a BrainKernel with mocked dependencies."""
        from unittest.mock import MagicMock

        from core.runtime.brain_kernel import BrainKernel

        mock_tool_runtime = MagicMock()
        mock_reasoning_engine = MagicMock()
        mock_memory_coordinator = MagicMock()

        kernel = BrainKernel.__new__(BrainKernel)
        kernel.tool_runtime = mock_tool_runtime
        kernel.reasoning_engine = mock_reasoning_engine
        kernel.memory_coordinator = mock_memory_coordinator
        kernel.identity_service = mock_identity_service
        return kernel

    @pytest.mark.asyncio
    async def test_get_active_identity_delegates_to_service(
        self, brain_kernel, mock_identity_service
    ) -> None:
        """BrainKernel.get_active_identity() delegates to IdentityService."""
        expected = _make_identity(is_active=True)
        mock_identity_service.get_active_identity = AsyncMock(return_value=expected)

        result = await brain_kernel.get_active_identity()
        assert result is expected
        mock_identity_service.get_active_identity.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_active_identity_no_service_falls_back(self) -> None:
        """BrainKernel.get_active_identity() returns None when service is absent."""
        from core.runtime.brain_kernel import BrainKernel

        kernel = BrainKernel.__new__(BrainKernel)
        kernel.identity_service = None

        result = await kernel.get_active_identity()
        assert result is None


# ===========================================================================
# 7. DEFAULT_IDENTITY invariant tests
# ===========================================================================


class TestDefaultIdentityInvariant:
    """Guard default identity shape and fallback behaviour."""

    def test_default_identity_has_wildcard_capability(self) -> None:
        """DEFAULT_IDENTITY allows all capabilities via '*'."""
        from core.reasoning.identity import DEFAULT_IDENTITY
        assert "*" in DEFAULT_IDENTITY.allowed_capabilities

    def test_default_identity_is_active(self) -> None:
        """DEFAULT_IDENTITY is flagged as active (serves as ultimate fallback)."""
        from core.reasoning.identity import DEFAULT_IDENTITY
        assert DEFAULT_IDENTITY.is_active is True

    def test_default_identity_has_admin_permission_profile(self) -> None:
        """DEFAULT_IDENTITY carries admin permission_profile."""
        from core.reasoning.identity import DEFAULT_IDENTITY
        assert DEFAULT_IDENTITY.permission_profile == "admin"

    def test_default_identity_system_prompt_not_empty(self) -> None:
        """DEFAULT_IDENTITY has a non-empty system prompt."""
        from core.reasoning.identity import DEFAULT_IDENTITY
        assert len(DEFAULT_IDENTITY.system_prompt) > 10
