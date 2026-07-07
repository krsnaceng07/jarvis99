"""
PHASE: 43
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/105_PHASE_43_GOAL_ENGINE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/21be4144-6686-48ed-8e46-74ce7e189cd4/implementation_plan.md

AUTHORITATIVE:
    NO

Tests: Goal Engine (Phase 43)
Covers: PersistentGoal DTO, GoalStatus enum, GoalRepository CRUD,
        GoalService lifecycle (create/activate/complete/cancel/progress/delete),
        event publishing, to_goal_dto mapper, API route handlers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_persistent_goal(**kwargs: Any):
    """Create a PersistentGoal with sensible defaults."""
    from core.reasoning.goal import PersistentGoal

    defaults: Dict[str, Any] = {
        "title": "Test Goal",
        "description": "A test goal description.",
        "priority": 5,
        "tags": ["test", "ci"],
        "metadata": {"source": "pytest"},
    }
    defaults.update(kwargs)
    return PersistentGoal(**defaults)


def _make_goal_model(**kwargs: Any):
    """Create an AgentGoalModel ORM instance with defaults."""
    from core.memory.models import AgentGoalModel

    defaults: Dict[str, Any] = {
        "id": uuid4(),
        "title": "Test Goal",
        "description": "A test goal.",
        "status": "pending",
        "priority": 5,
        "progress": 0.0,
        "identity_id": None,
        "parent_goal_id": None,
        "tags": ["test"],
        "metadata_": {"source": "pytest"},
        "due_at": None,
        "completed_at": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    defaults.update(kwargs)
    return AgentGoalModel(**defaults)


# ===========================================================================
# 1. PersistentGoal DTO tests
# ===========================================================================


class TestPersistentGoalDTO:
    """Unit tests for the PersistentGoal Pydantic model."""

    def test_create_minimal_goal(self) -> None:
        """PersistentGoal can be created with only the required title."""
        from core.reasoning.goal import PersistentGoal

        goal = PersistentGoal(title="Minimal Goal")
        assert goal.title == "Minimal Goal"
        assert goal.status.value == "pending"
        assert goal.priority == 5
        assert goal.progress == 0.0
        assert goal.tags == []
        assert goal.metadata == {}

    def test_create_full_goal(self) -> None:
        """PersistentGoal stores all fields correctly."""
        goal = _make_persistent_goal(priority=9, tags=["research"])
        assert goal.priority == 9
        assert "research" in goal.tags

    def test_goal_has_auto_uuid(self) -> None:
        """PersistentGoal auto-generates unique UUIDs."""
        from core.reasoning.goal import PersistentGoal

        a = PersistentGoal(title="A")
        b = PersistentGoal(title="B")
        assert a.id != b.id
        assert isinstance(a.id, UUID)

    def test_progress_out_of_range_above_raises(self) -> None:
        """Progress values above 100 raise ValidationError (ge/le constraint)."""
        from core.reasoning.goal import PersistentGoal

        with pytest.raises(ValidationError):
            PersistentGoal(title="G", progress=150.0)

    def test_progress_out_of_range_below_raises(self) -> None:
        """Progress values below 0 raise ValidationError (ge=0.0 constraint)."""
        from core.reasoning.goal import PersistentGoal

        with pytest.raises(ValidationError):
            PersistentGoal(title="G", progress=-10.0)

    def test_priority_out_of_range_raises(self) -> None:
        """Priority outside [1, 10] raises ValidationError."""
        from core.reasoning.goal import PersistentGoal

        with pytest.raises(ValidationError):
            PersistentGoal(title="G", priority=11)

    def test_timestamps_are_tz_aware(self) -> None:
        """created_at and updated_at carry timezone info."""
        goal = _make_persistent_goal()
        assert goal.created_at.tzinfo is not None
        assert goal.updated_at.tzinfo is not None

    def test_missing_title_raises(self) -> None:
        """Missing required title raises ValidationError."""
        from core.reasoning.goal import PersistentGoal

        with pytest.raises(ValidationError):
            PersistentGoal()


# ===========================================================================
# 2. GoalStatus enum tests
# ===========================================================================


class TestGoalStatus:
    """Tests for GoalStatus enum values."""

    def test_all_statuses_exist(self) -> None:
        """All expected status values are present."""
        from core.reasoning.goal import GoalStatus

        assert GoalStatus.PENDING.value == "pending"
        assert GoalStatus.ACTIVE.value == "active"
        assert GoalStatus.PAUSED.value == "paused"
        assert GoalStatus.COMPLETED.value == "completed"
        assert GoalStatus.CANCELLED.value == "cancelled"

    def test_status_from_string(self) -> None:
        """GoalStatus can be constructed from a string value."""
        from core.reasoning.goal import GoalStatus

        assert GoalStatus("active") == GoalStatus.ACTIVE

    def test_invalid_status_raises(self) -> None:
        """Invalid string raises ValueError."""
        from core.reasoning.goal import GoalStatus

        with pytest.raises(ValueError):
            GoalStatus("flying")


# ===========================================================================
# 3. GoalRepository unit tests
# ===========================================================================


class TestGoalRepository:
    """Unit tests for GoalRepository using mock AsyncSession."""

    @pytest.fixture
    def repo(self):
        from core.reasoning.goal_repository import GoalRepository
        return GoalRepository()

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        session.delete = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_save_goal(self, repo, mock_session) -> None:
        """save_goal adds model and flushes."""
        model = _make_goal_model()
        await repo.save_goal(model, mock_session)
        mock_session.add.assert_called_once_with(model)
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_goal_found(self, repo, mock_session) -> None:
        """get_goal returns model when found."""
        model = _make_goal_model()
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = model
        mock_session.execute = AsyncMock(return_value=result_mock)

        found = await repo.get_goal(model.id, mock_session)
        assert found is model

    @pytest.mark.asyncio
    async def test_get_goal_not_found(self, repo, mock_session) -> None:
        """get_goal returns None for unknown ID."""
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=result_mock)

        found = await repo.get_goal(uuid4(), mock_session)
        assert found is None

    @pytest.mark.asyncio
    async def test_list_goals_no_filter(self, repo, mock_session) -> None:
        """list_goals returns all rows when no filter given."""
        models = [_make_goal_model(), _make_goal_model()]
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = models
        mock_session.execute = AsyncMock(return_value=result_mock)

        result = await repo.list_goals(mock_session)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_list_goals_with_status_filter(self, repo, mock_session) -> None:
        """list_goals passes status filter through to query."""
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=result_mock)

        result = await repo.list_goals(mock_session, status="active")
        assert result == []
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_goal(self, repo, mock_session) -> None:
        """update_goal executes an UPDATE statement and flushes."""
        mock_session.execute = AsyncMock()
        mock_session.flush = AsyncMock()

        await repo.update_goal(uuid4(), {"title": "Updated"}, mock_session)
        mock_session.execute.assert_awaited_once()
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_goal_found(self, repo, mock_session) -> None:
        """delete_goal returns True and deletes when row exists."""
        model = _make_goal_model()
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = model
        mock_session.execute = AsyncMock(return_value=result_mock)
        mock_session.delete = AsyncMock()
        mock_session.flush = AsyncMock()

        deleted = await repo.delete_goal(model.id, mock_session)
        assert deleted is True
        mock_session.delete.assert_awaited_once_with(model)

    @pytest.mark.asyncio
    async def test_delete_goal_not_found(self, repo, mock_session) -> None:
        """delete_goal returns False when row not found."""
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = None
        mock_session.execute = AsyncMock(return_value=result_mock)

        deleted = await repo.delete_goal(uuid4(), mock_session)
        assert deleted is False


# ===========================================================================
# 4. GoalService unit tests
# ===========================================================================


class TestGoalService:
    """Unit tests for GoalService lifecycle methods."""

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
        from core.reasoning.goal import GoalService
        return GoalService(repository=mock_repo, event_bus=mock_event_bus)

    # -----------------------------------------------------------------------
    # create_goal
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_goal_publishes_event(
        self, service, mock_repo, mock_event_bus
    ) -> None:
        """create_goal emits goal.created event."""
        goal = _make_persistent_goal()

        with patch("core.memory.database.db_manager") as mock_db:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_sess.commit = AsyncMock()
            mock_db.session.return_value = mock_sess
            mock_repo.save_goal = AsyncMock()

            result = await service.create_goal(goal)

        assert result.title == goal.title
        mock_event_bus.publish.assert_awaited_once()
        assert mock_event_bus.publish.call_args[0][0] == "goal.created"

    # -----------------------------------------------------------------------
    # get_goal
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_get_goal_returns_dto(self, service, mock_repo) -> None:
        """get_goal returns a PersistentGoal DTO when found."""
        model = _make_goal_model()
        with patch("core.memory.database.db_manager") as mock_db:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_db.session.return_value = mock_sess
            mock_repo.get_goal = AsyncMock(return_value=model)

            result = await service.get_goal(model.id)

        from core.reasoning.goal import PersistentGoal
        assert isinstance(result, PersistentGoal)

    @pytest.mark.asyncio
    async def test_get_goal_not_found_returns_none(
        self, service, mock_repo
    ) -> None:
        """get_goal returns None for unknown ID."""
        with patch("core.memory.database.db_manager") as mock_db:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_db.session.return_value = mock_sess
            mock_repo.get_goal = AsyncMock(return_value=None)

            result = await service.get_goal(uuid4())

        assert result is None

    # -----------------------------------------------------------------------
    # activate_goal
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_activate_goal_publishes_updated_event(
        self, service, mock_repo, mock_event_bus
    ) -> None:
        """activate_goal triggers goal.updated event via update_goal."""
        model = _make_goal_model(status="pending")

        with patch("core.memory.database.db_manager") as mock_db:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_sess.commit = AsyncMock()
            mock_db.session.return_value = mock_sess
            mock_repo.get_goal = AsyncMock(return_value=model)
            mock_repo.update_goal = AsyncMock()

            await service.activate_goal(model.id)

        mock_event_bus.publish.assert_awaited()
        # goal.updated is published
        published_events = [
            call[0][0] for call in mock_event_bus.publish.call_args_list
        ]
        assert "goal.updated" in published_events

    @pytest.mark.asyncio
    async def test_activate_goal_not_found_raises(
        self, service, mock_repo
    ) -> None:
        """activate_goal raises ValueError for unknown ID."""
        with patch("core.memory.database.db_manager") as mock_db:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_db.session.return_value = mock_sess
            mock_repo.get_goal = AsyncMock(return_value=None)

            with pytest.raises(ValueError, match="not found"):
                await service.activate_goal(uuid4())

    # -----------------------------------------------------------------------
    # complete_goal
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_complete_goal_publishes_completed_event(
        self, service, mock_repo, mock_event_bus
    ) -> None:
        """complete_goal emits both goal.updated and goal.completed."""
        model = _make_goal_model(status="active", progress=50.0)

        with patch("core.memory.database.db_manager") as mock_db:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_sess.commit = AsyncMock()
            mock_db.session.return_value = mock_sess
            mock_repo.get_goal = AsyncMock(return_value=model)
            mock_repo.update_goal = AsyncMock()

            await service.complete_goal(model.id)

        published_events = [
            call[0][0] for call in mock_event_bus.publish.call_args_list
        ]
        assert "goal.completed" in published_events

    # -----------------------------------------------------------------------
    # cancel_goal
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_cancel_goal(self, service, mock_repo, mock_event_bus) -> None:
        """cancel_goal triggers goal.updated event."""
        model = _make_goal_model()

        with patch("core.memory.database.db_manager") as mock_db:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_sess.commit = AsyncMock()
            mock_db.session.return_value = mock_sess
            mock_repo.get_goal = AsyncMock(return_value=model)
            mock_repo.update_goal = AsyncMock()

            await service.cancel_goal(model.id)

        mock_event_bus.publish.assert_awaited()

    # -----------------------------------------------------------------------
    # update_progress
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_update_progress_partial(
        self, service, mock_repo, mock_event_bus
    ) -> None:
        """update_progress below 100 only fires goal.updated."""
        model = _make_goal_model(progress=30.0)

        with patch("core.memory.database.db_manager") as mock_db:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_sess.commit = AsyncMock()
            mock_db.session.return_value = mock_sess
            mock_repo.get_goal = AsyncMock(return_value=model)
            mock_repo.update_goal = AsyncMock()

            await service.update_progress(model.id, 60.0)

        published_events = [
            call[0][0] for call in mock_event_bus.publish.call_args_list
        ]
        assert "goal.completed" not in published_events

    @pytest.mark.asyncio
    async def test_update_progress_auto_completes_at_100(
        self, service, mock_repo, mock_event_bus
    ) -> None:
        """update_progress at 100 also fires goal.completed."""
        model = _make_goal_model(progress=50.0)

        with patch("core.memory.database.db_manager") as mock_db:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_sess.commit = AsyncMock()
            mock_db.session.return_value = mock_sess
            mock_repo.get_goal = AsyncMock(return_value=model)
            mock_repo.update_goal = AsyncMock()

            await service.update_progress(model.id, 100.0)

        published_events = [
            call[0][0] for call in mock_event_bus.publish.call_args_list
        ]
        assert "goal.completed" in published_events

    # -----------------------------------------------------------------------
    # delete_goal
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_delete_goal_returns_true(
        self, service, mock_repo
    ) -> None:
        """delete_goal returns True on success."""
        with patch("core.memory.database.db_manager") as mock_db:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_sess.commit = AsyncMock()
            mock_db.session.return_value = mock_sess
            mock_repo.delete_goal = AsyncMock(return_value=True)

            result = await service.delete_goal(uuid4())

        assert result is True

    @pytest.mark.asyncio
    async def test_delete_goal_returns_false_when_not_found(
        self, service, mock_repo
    ) -> None:
        """delete_goal returns False for unknown ID."""
        with patch("core.memory.database.db_manager") as mock_db:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_sess.commit = AsyncMock()
            mock_db.session.return_value = mock_sess
            mock_repo.delete_goal = AsyncMock(return_value=False)

            result = await service.delete_goal(uuid4())

        assert result is False

    # -----------------------------------------------------------------------
    # list_goals / get_active_goals
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_list_goals_returns_dtos(
        self, service, mock_repo
    ) -> None:
        """list_goals returns PersistentGoal DTOs."""
        models = [_make_goal_model(), _make_goal_model()]
        with patch("core.memory.database.db_manager") as mock_db:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_db.session.return_value = mock_sess
            mock_repo.list_goals = AsyncMock(return_value=models)

            result = await service.list_goals()

        assert len(result) == 2
        from core.reasoning.goal import PersistentGoal
        for item in result:
            assert isinstance(item, PersistentGoal)

    @pytest.mark.asyncio
    async def test_get_active_goals_filters_by_active(
        self, service, mock_repo
    ) -> None:
        """get_active_goals passes ACTIVE status filter."""
        with patch("core.memory.database.db_manager") as mock_db:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_db.session.return_value = mock_sess
            mock_repo.list_goals = AsyncMock(return_value=[])

            await service.get_active_goals()

        call_kwargs = mock_repo.list_goals.call_args[1]
        assert call_kwargs.get("status") == "active"

    # -----------------------------------------------------------------------
    # No event bus — graceful degradation
    # -----------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_create_goal_no_event_bus(self, mock_repo) -> None:
        """GoalService works without an event bus (no publish call)."""
        from core.reasoning.goal import GoalService

        service_no_bus = GoalService(repository=mock_repo, event_bus=None)
        goal = _make_persistent_goal()

        with patch("core.memory.database.db_manager") as mock_db:
            mock_sess = AsyncMock()
            mock_sess.__aenter__ = AsyncMock(return_value=mock_sess)
            mock_sess.__aexit__ = AsyncMock(return_value=False)
            mock_sess.commit = AsyncMock()
            mock_db.session.return_value = mock_sess
            mock_repo.save_goal = AsyncMock()

            result = await service_no_bus.create_goal(goal)

        assert result.title == goal.title


# ===========================================================================
# 5. to_goal_dto mapping tests
# ===========================================================================


class TestGoalDTOMapping:
    """Tests for the to_goal_dto helper function."""

    def test_to_goal_dto_maps_all_fields(self) -> None:
        """to_goal_dto maps all fields correctly."""
        from core.memory.models import to_goal_dto
        from core.reasoning.goal import PersistentGoal

        model = _make_goal_model(title="Mapped", status="active", progress=42.0)
        dto = to_goal_dto(model)

        assert isinstance(dto, PersistentGoal)
        assert dto.id == model.id
        assert dto.title == "Mapped"
        assert dto.status.value == "active"
        assert dto.progress == 42.0
        assert dto.metadata == model.metadata_

    def test_to_goal_dto_handles_none_optionals(self) -> None:
        """to_goal_dto handles None optional fields."""
        from core.memory.models import to_goal_dto

        model = _make_goal_model(
            description=None,
            identity_id=None,
            parent_goal_id=None,
            due_at=None,
            completed_at=None,
        )
        dto = to_goal_dto(model)
        assert dto.description is None
        assert dto.identity_id is None
        assert dto.due_at is None


# ===========================================================================
# 6. API Route handler tests
# ===========================================================================


class TestGoalRoutes:
    """Integration-style tests for goal route handlers with mocked service."""

    @pytest.fixture
    def mock_service(self):
        return AsyncMock()

    @pytest.fixture
    def client(self, mock_service):
        """Create a TestClient with the goal router and mocked service."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from api.dependencies import get_goal_service
        from api.routes.goal import router

        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_goal_service] = lambda: mock_service

        return TestClient(app)

    def test_list_goals_empty(self, client, mock_service) -> None:
        """GET /goals returns empty list."""
        mock_service.list_goals = AsyncMock(return_value=[])
        response = client.get("/goals")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_goals_with_data(self, client, mock_service) -> None:
        """GET /goals returns serialised goals."""
        goal = _make_persistent_goal(title="My Goal")
        mock_service.list_goals = AsyncMock(return_value=[goal])

        response = client.get("/goals")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["title"] == "My Goal"

    def test_create_goal_success(self, client, mock_service) -> None:
        """POST /goals creates and returns goal."""
        goal = _make_persistent_goal(title="New Goal")
        mock_service.create_goal = AsyncMock(return_value=goal)

        response = client.post("/goals", json={"title": "New Goal"})
        assert response.status_code == 201
        assert response.json()["title"] == "New Goal"

    def test_create_goal_missing_title(self, client, mock_service) -> None:
        """POST /goals without title returns 422."""
        response = client.post("/goals", json={"priority": 3})
        assert response.status_code == 422

    def test_get_goal_found(self, client, mock_service) -> None:
        """GET /goals/{id} returns goal."""
        goal = _make_persistent_goal()
        mock_service.get_goal = AsyncMock(return_value=goal)

        response = client.get(f"/goals/{goal.id}")
        assert response.status_code == 200
        assert response.json()["id"] == str(goal.id)

    def test_get_goal_not_found(self, client, mock_service) -> None:
        """GET /goals/{id} returns 404 for unknown goal."""
        mock_service.get_goal = AsyncMock(return_value=None)
        response = client.get(f"/goals/{uuid4()}")
        assert response.status_code == 404

    def test_activate_goal_success(self, client, mock_service) -> None:
        """POST /goals/{id}/activate returns updated goal."""
        from core.reasoning.goal import GoalStatus
        goal = _make_persistent_goal(status=GoalStatus.ACTIVE)
        mock_service.activate_goal = AsyncMock(return_value=goal)

        response = client.post(f"/goals/{goal.id}/activate")
        assert response.status_code == 200
        assert response.json()["status"] == "active"

    def test_activate_goal_not_found(self, client, mock_service) -> None:
        """POST /goals/{id}/activate returns 404 for unknown ID."""
        mock_service.activate_goal = AsyncMock(
            side_effect=ValueError("Goal x not found.")
        )
        response = client.post(f"/goals/{uuid4()}/activate")
        assert response.status_code == 404

    def test_complete_goal_success(self, client, mock_service) -> None:
        """POST /goals/{id}/complete returns 200."""
        from core.reasoning.goal import GoalStatus
        goal = _make_persistent_goal(status=GoalStatus.COMPLETED, progress=100.0)
        mock_service.complete_goal = AsyncMock(return_value=goal)

        response = client.post(f"/goals/{goal.id}/complete")
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

    def test_cancel_goal_success(self, client, mock_service) -> None:
        """POST /goals/{id}/cancel returns 200."""
        from core.reasoning.goal import GoalStatus
        goal = _make_persistent_goal(status=GoalStatus.CANCELLED)
        mock_service.cancel_goal = AsyncMock(return_value=goal)

        response = client.post(f"/goals/{goal.id}/cancel")
        assert response.status_code == 200
        assert response.json()["status"] == "cancelled"

    def test_update_progress_success(self, client, mock_service) -> None:
        """POST /goals/{id}/progress returns updated goal."""
        goal = _make_persistent_goal(progress=75.0)
        mock_service.update_progress = AsyncMock(return_value=goal)

        response = client.post(
            f"/goals/{goal.id}/progress", json={"progress": 75.0}
        )
        assert response.status_code == 200
        assert response.json()["progress"] == 75.0

    def test_update_progress_out_of_range(self, client, mock_service) -> None:
        """POST /goals/{id}/progress with invalid range returns 422."""
        response = client.post(
            f"/goals/{uuid4()}/progress", json={"progress": 150.0}
        )
        assert response.status_code == 422

    def test_delete_goal_success(self, client, mock_service) -> None:
        """DELETE /goals/{id} returns 204."""
        mock_service.delete_goal = AsyncMock(return_value=True)
        response = client.delete(f"/goals/{uuid4()}")
        assert response.status_code == 204

    def test_delete_goal_not_found(self, client, mock_service) -> None:
        """DELETE /goals/{id} returns 404 for unknown ID."""
        mock_service.delete_goal = AsyncMock(return_value=False)
        response = client.delete(f"/goals/{uuid4()}")
        assert response.status_code == 404

    def test_list_goals_service_error(self, client, mock_service) -> None:
        """GET /goals returns 500 on service error."""
        mock_service.list_goals = AsyncMock(
            side_effect=RuntimeError("DB gone")
        )
        response = client.get("/goals")
        assert response.status_code == 500
