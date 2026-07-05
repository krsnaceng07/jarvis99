"""
PHASE: 15
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/77_PHASE_15_PERSISTENT_EXECUTION_SPECIFICATION.md

IMPLEMENTATION PLAN:
    docs/implementation_plan.md

AUTHORITATIVE:
    NO
"""

import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.dto import (
    AgentRunsHistoryResponse,
    AgentRunStatusResponse,
    SessionState,
    SuccessEnvelope,
    WorkflowExecutionsHistoryResponse,
    WorkflowState,
    WorkflowStatusResponse,
)
from core.tools.execution_models import (
    AgentRunModel,
    WorkflowExecutionModel,
    WorkflowStepExecutionModel,
)
from core.tools.execution_repository import ExecutionRepository

# ---------------------------------------------------------------------------
# Shared mock factory for `async with db_manager.session() as s: async with s.begin():`
# ---------------------------------------------------------------------------


def _make_db_manager_mock() -> MagicMock:
    """Build a mock db_manager whose .session() yields a session with .begin()."""
    mock_session = AsyncMock()

    @asynccontextmanager
    async def _begin() -> AsyncGenerator[None, None]:
        yield

    mock_session.begin = _begin

    @asynccontextmanager
    async def _session_ctx() -> AsyncGenerator[AsyncMock, None]:
        yield mock_session

    mock_db = MagicMock()
    mock_db.session = _session_ctx
    return mock_db


# ---------------------------------------------------------------------------
# 1. DTO Tests — Phase 15 history wrapper DTOs
# ---------------------------------------------------------------------------


def test_agent_runs_history_response_empty() -> None:
    resp = AgentRunsHistoryResponse(runs=[])
    assert resp.runs == []
    assert resp.api_version == "v1"


def test_agent_runs_history_response_with_items() -> None:
    run_id = uuid.uuid4()
    item = AgentRunStatusResponse(run_id=run_id, state=SessionState.COMPLETED)
    resp = AgentRunsHistoryResponse(runs=[item])
    assert len(resp.runs) == 1
    assert resp.runs[0].run_id == run_id
    assert resp.runs[0].state == SessionState.COMPLETED
    assert resp.api_version == "v1"


def test_workflow_executions_history_response_empty() -> None:
    resp = WorkflowExecutionsHistoryResponse(executions=[])
    assert resp.executions == []
    assert resp.api_version == "v1"


def test_workflow_executions_history_response_with_items() -> None:
    wf_id = uuid.uuid4()
    item = WorkflowStatusResponse(workflow_id=wf_id, state=WorkflowState.COMPLETED)
    resp = WorkflowExecutionsHistoryResponse(executions=[item])
    assert len(resp.executions) == 1
    assert resp.executions[0].workflow_id == wf_id
    assert resp.executions[0].state == WorkflowState.COMPLETED


def test_agent_runs_history_in_envelope() -> None:
    run_id = uuid.uuid4()
    item = AgentRunStatusResponse(run_id=run_id, state=SessionState.PLANNING)
    history = AgentRunsHistoryResponse(runs=[item])
    envelope = SuccessEnvelope[AgentRunsHistoryResponse](data=history)
    assert envelope.success is True
    assert len(envelope.data.runs) == 1
    json_dict = envelope.model_dump(mode="json")
    assert json_dict["data"]["runs"][0]["state"] == "Planning"


# ---------------------------------------------------------------------------
# 2. ORM Model Tests — Execution Models
# ---------------------------------------------------------------------------


def test_agent_run_model_fields() -> None:
    run_id = uuid.uuid4()
    model = AgentRunModel(
        id=run_id,
        goal="Test goal",
        budget=5.0,
        state="Planning",
    )
    assert model.id == run_id
    assert model.goal == "Test goal"
    assert model.budget == 5.0
    assert model.state == "Planning"
    assert model.metrics is None
    assert model.failure_type is None


def test_agent_run_model_with_failure() -> None:
    run_id = uuid.uuid4()
    model = AgentRunModel(
        id=run_id,
        goal="Failing goal",
        budget=10.0,
        state="Failed",
        failure_type="PlannerFailure",
        metrics={"total_tokens": 100},
    )
    assert model.state == "Failed"
    assert model.failure_type == "PlannerFailure"
    assert model.metrics == {"total_tokens": 100}


def test_workflow_execution_model_fields() -> None:
    exec_id = uuid.uuid4()
    wf_id = uuid.uuid4()
    model = WorkflowExecutionModel(
        id=exec_id,
        workflow_id=wf_id,
        version=2,
        state="RUNNING",
    )
    assert model.id == exec_id
    assert model.workflow_id == wf_id
    assert model.version == 2
    assert model.state == "RUNNING"
    assert model.metrics is None


def test_workflow_step_execution_model_fields() -> None:
    exec_id = uuid.uuid4()
    model = WorkflowStepExecutionModel(
        execution_id=exec_id,
        step_name="step_1",
        state="RUNNING",
        attempts=1,
    )
    assert model.execution_id == exec_id
    assert model.step_name == "step_1"
    assert model.state == "RUNNING"
    assert model.attempts == 1
    assert model.output is None
    assert model.error is None


def test_workflow_step_execution_model_with_output_and_error() -> None:
    exec_id = uuid.uuid4()
    model = WorkflowStepExecutionModel(
        execution_id=exec_id,
        step_name="step_2",
        state="FAILED",
        attempts=3,
        output={"result": "partial"},
        error={"error": "timeout"},
    )
    assert model.attempts == 3
    assert model.output == {"result": "partial"}
    assert model.error == {"error": "timeout"}


# ---------------------------------------------------------------------------
# 3. PersistenceService Tests — EventBus subscription and dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_persistence_service_initialize_subscribes_events() -> None:
    from core.reasoning.persistence_service import PersistenceService

    mock_repo = MagicMock(spec=ExecutionRepository)
    mock_bus = AsyncMock()

    service = PersistenceService(repository=mock_repo, event_bus=mock_bus)
    await service.initialize()

    expected_topics = [
        "engine.state.transition",
        "workflow.started",
        "workflow.completed",
        "workflow.step.started",
        "workflow.step.completed",
        "workflow.step.failed",
        "journal.iteration.recorded",
    ]
    assert mock_bus.subscribe.call_count == len(expected_topics)
    subscribed_topics = [call.args[0] for call in mock_bus.subscribe.call_args_list]
    for topic in expected_topics:
        assert topic in subscribed_topics


@pytest.mark.asyncio
async def test_persistence_service_start_stop_shutdown_noop() -> None:
    from core.reasoning.persistence_service import PersistenceService

    mock_repo = MagicMock(spec=ExecutionRepository)
    mock_bus = AsyncMock()

    service = PersistenceService(repository=mock_repo, event_bus=mock_bus)
    await service.start()
    await service.stop()
    await service.shutdown()


@pytest.mark.asyncio
async def test_persistence_service_handles_engine_transition() -> None:
    from core.interfaces import InterAgentMessage
    from core.reasoning.persistence_service import PersistenceService, active_run_id

    mock_repo = AsyncMock(spec=ExecutionRepository)
    mock_bus = AsyncMock()

    service = PersistenceService(repository=mock_repo, event_bus=mock_bus)

    run_id = uuid.uuid4()
    trace_id = uuid.uuid4()

    token = active_run_id.set(run_id)

    msg = InterAgentMessage(
        sender="engine",
        receiver="persistence",
        action="engine.state.transition",
        correlation_id=trace_id,
        body={"state": "Executing"},
    )

    mock_db = _make_db_manager_mock()
    with patch("core.reasoning.persistence_service.db_manager", mock_db):
        await service.handle_engine_transition(msg)

        mock_repo.update_agent_run_state.assert_called_once()
        call_kwargs = mock_repo.update_agent_run_state.call_args.kwargs
        assert call_kwargs["run_id"] == run_id
        assert call_kwargs["state"] == "Executing"

    active_run_id.reset(token)


@pytest.mark.asyncio
async def test_persistence_service_ignores_empty_state() -> None:
    from core.interfaces import InterAgentMessage
    from core.reasoning.persistence_service import PersistenceService

    mock_repo = AsyncMock(spec=ExecutionRepository)
    mock_bus = AsyncMock()

    service = PersistenceService(repository=mock_repo, event_bus=mock_bus)

    msg = InterAgentMessage(
        sender="engine",
        receiver="persistence",
        action="engine.state.transition",
        body={},
    )

    await service.handle_engine_transition(msg)
    mock_repo.update_agent_run_state.assert_not_called()


@pytest.mark.asyncio
async def test_persistence_service_handles_workflow_started() -> None:
    from core.interfaces import InterAgentMessage
    from core.reasoning.persistence_service import PersistenceService

    mock_repo = AsyncMock(spec=ExecutionRepository)
    mock_bus = AsyncMock()

    service = PersistenceService(repository=mock_repo, event_bus=mock_bus)

    exec_id = uuid.uuid4()
    wf_id = uuid.uuid4()
    msg = InterAgentMessage(
        sender="orchestrator",
        receiver="persistence",
        action="workflow.started",
        correlation_id=exec_id,
        body={"workflow_id": str(wf_id), "state": "RUNNING"},
    )

    mock_db = _make_db_manager_mock()
    with patch("core.reasoning.persistence_service.db_manager", mock_db):
        with patch("core.tools.repository.WorkflowRepository") as mock_wf_repo_cls:
            mock_wf_repo = AsyncMock()
            mock_wf_repo.get.return_value = MagicMock(version=3)
            mock_wf_repo_cls.return_value = mock_wf_repo

            await service.handle_workflow_started(msg)

            mock_repo.save_workflow_execution.assert_called_once()
            call_kwargs = mock_repo.save_workflow_execution.call_args.kwargs
            assert call_kwargs["execution_id"] == exec_id
            assert call_kwargs["workflow_id"] == wf_id
            assert call_kwargs["version"] == 3
            assert call_kwargs["state"] == "RUNNING"


@pytest.mark.asyncio
async def test_persistence_service_handles_workflow_completed() -> None:
    from core.interfaces import InterAgentMessage
    from core.reasoning.persistence_service import PersistenceService

    mock_repo = AsyncMock(spec=ExecutionRepository)
    mock_bus = AsyncMock()

    service = PersistenceService(repository=mock_repo, event_bus=mock_bus)

    exec_id = uuid.uuid4()
    msg = InterAgentMessage(
        sender="orchestrator",
        receiver="persistence",
        action="workflow.completed",
        correlation_id=exec_id,
        body={"state": "COMPLETED", "metrics": {"steps_completed": 5}},
    )

    mock_db = _make_db_manager_mock()
    with patch("core.reasoning.persistence_service.db_manager", mock_db):
        await service.handle_workflow_completed(msg)

        mock_repo.update_workflow_execution.assert_called_once()
        call_kwargs = mock_repo.update_workflow_execution.call_args.kwargs
        assert call_kwargs["execution_id"] == exec_id
        assert call_kwargs["state"] == "COMPLETED"
        assert call_kwargs["metrics"] == {"steps_completed": 5}


@pytest.mark.asyncio
async def test_persistence_service_handles_step_started() -> None:
    from core.interfaces import InterAgentMessage
    from core.reasoning.persistence_service import PersistenceService

    mock_repo = AsyncMock(spec=ExecutionRepository)
    mock_bus = AsyncMock()

    service = PersistenceService(repository=mock_repo, event_bus=mock_bus)

    exec_id = uuid.uuid4()
    msg = InterAgentMessage(
        sender="orchestrator",
        receiver="persistence",
        action="workflow.step.started",
        correlation_id=exec_id,
        body={"step_name": "step_alpha", "state": "RUNNING"},
    )

    mock_db = _make_db_manager_mock()
    with patch("core.reasoning.persistence_service.db_manager", mock_db):
        await service.handle_step_started(msg)

        mock_repo.save_step_execution.assert_called_once()
        call_kwargs = mock_repo.save_step_execution.call_args.kwargs
        assert call_kwargs["step_name"] == "step_alpha"
        assert call_kwargs["state"] == "RUNNING"
        assert call_kwargs["attempts"] == 1


@pytest.mark.asyncio
async def test_persistence_service_handles_step_completed() -> None:
    from core.interfaces import InterAgentMessage
    from core.reasoning.persistence_service import PersistenceService

    mock_repo = AsyncMock(spec=ExecutionRepository)
    mock_bus = AsyncMock()

    service = PersistenceService(repository=mock_repo, event_bus=mock_bus)

    exec_id = uuid.uuid4()
    msg = InterAgentMessage(
        sender="orchestrator",
        receiver="persistence",
        action="workflow.step.completed",
        correlation_id=exec_id,
        body={"step_name": "step_beta", "state": "COMPLETED", "output": {"data": 42}},
    )

    mock_db = _make_db_manager_mock()
    with patch("core.reasoning.persistence_service.db_manager", mock_db):
        await service.handle_step_completed(msg)

        mock_repo.save_step_execution.assert_called_once()
        call_kwargs = mock_repo.save_step_execution.call_args.kwargs
        assert call_kwargs["step_name"] == "step_beta"
        assert call_kwargs["state"] == "COMPLETED"
        assert call_kwargs["output"] == {"data": 42}


@pytest.mark.asyncio
async def test_persistence_service_handles_step_failed() -> None:
    from core.interfaces import InterAgentMessage
    from core.reasoning.persistence_service import PersistenceService

    mock_repo = AsyncMock(spec=ExecutionRepository)
    mock_bus = AsyncMock()

    service = PersistenceService(repository=mock_repo, event_bus=mock_bus)

    exec_id = uuid.uuid4()
    msg = InterAgentMessage(
        sender="orchestrator",
        receiver="persistence",
        action="workflow.step.failed",
        correlation_id=exec_id,
        body={
            "step_name": "step_gamma",
            "state": "FAILED",
            "error": "timeout reached",
        },
    )

    mock_db = _make_db_manager_mock()
    with patch("core.reasoning.persistence_service.db_manager", mock_db):
        await service.handle_step_failed(msg)

        mock_repo.save_step_execution.assert_called_once()
        call_kwargs = mock_repo.save_step_execution.call_args.kwargs
        assert call_kwargs["step_name"] == "step_gamma"
        assert call_kwargs["state"] == "FAILED"
        assert call_kwargs["error"] == {"error": "timeout reached"}


@pytest.mark.asyncio
async def test_persistence_service_step_ignores_missing_fields() -> None:
    from core.interfaces import InterAgentMessage
    from core.reasoning.persistence_service import PersistenceService

    mock_repo = AsyncMock(spec=ExecutionRepository)
    mock_bus = AsyncMock()
    service = PersistenceService(repository=mock_repo, event_bus=mock_bus)

    msg = InterAgentMessage(
        sender="orchestrator",
        receiver="persistence",
        action="workflow.step.started",
        body={"state": "RUNNING"},
    )
    await service.handle_step_started(msg)
    mock_repo.save_step_execution.assert_not_called()

    msg2 = InterAgentMessage(
        sender="orchestrator",
        receiver="persistence",
        action="workflow.step.started",
        body={"step_name": "s1"},
    )
    await service.handle_step_started(msg2)
    mock_repo.save_step_execution.assert_not_called()


# ---------------------------------------------------------------------------
# 4. ResumeManager Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resume_manager_recovers_stale_agent_runs() -> None:
    from core.tools.resume_manager import ResumeManager

    run_id_1 = uuid.uuid4()
    run_id_2 = uuid.uuid4()

    mock_repo = AsyncMock(spec=ExecutionRepository)
    mock_repo.get_active_agent_run_ids.return_value = [run_id_1, run_id_2]
    mock_repo.get_active_workflow_run_ids.return_value = []

    mock_bus = AsyncMock()
    manager = ResumeManager(repository=mock_repo, event_bus=mock_bus)

    mock_db = _make_db_manager_mock()
    with patch("core.tools.resume_manager.db_manager", mock_db):
        await manager.resume_all()

        assert mock_repo.update_agent_run_state.call_count == 2
        assert mock_bus.publish.call_count == 2

        for call in mock_repo.update_agent_run_state.call_args_list:
            assert call.kwargs["state"] == "Failed"
            assert call.kwargs["failure_type"] == "TimeoutFailure"


@pytest.mark.asyncio
async def test_resume_manager_recovers_stale_workflow_runs() -> None:
    from core.tools.resume_manager import ResumeManager

    exec_id = uuid.uuid4()

    mock_repo = AsyncMock(spec=ExecutionRepository)
    mock_repo.get_active_agent_run_ids.return_value = []
    mock_repo.get_active_workflow_run_ids.return_value = [exec_id]

    mock_step = MagicMock()
    mock_step.state = "RUNNING"
    mock_step.step_name = "step_1"
    mock_step.attempts = 1
    mock_repo.get_step_executions.return_value = [mock_step]

    mock_bus = AsyncMock()
    manager = ResumeManager(repository=mock_repo, event_bus=mock_bus)

    mock_db = _make_db_manager_mock()
    with patch("core.tools.resume_manager.db_manager", mock_db):
        await manager.resume_all()

        mock_repo.update_workflow_execution.assert_called_once()
        wf_kwargs = mock_repo.update_workflow_execution.call_args.kwargs
        assert wf_kwargs["state"] == "FAILED"

        mock_repo.save_step_execution.assert_called_once()
        step_kwargs = mock_repo.save_step_execution.call_args.kwargs
        assert step_kwargs["state"] == "FAILED"

        assert mock_bus.publish.call_count >= 2


@pytest.mark.asyncio
async def test_resume_manager_noop_when_no_stale_runs() -> None:
    from core.tools.resume_manager import ResumeManager

    mock_repo = AsyncMock(spec=ExecutionRepository)
    mock_repo.get_active_agent_run_ids.return_value = []
    mock_repo.get_active_workflow_run_ids.return_value = []

    mock_bus = AsyncMock()
    manager = ResumeManager(repository=mock_repo, event_bus=mock_bus)

    mock_db = _make_db_manager_mock()
    with patch("core.tools.resume_manager.db_manager", mock_db):
        await manager.resume_all()

        mock_repo.update_agent_run_state.assert_not_called()
        mock_repo.update_workflow_execution.assert_not_called()
        mock_bus.publish.assert_not_called()


# ---------------------------------------------------------------------------
# 5. API Route Integration Tests — agent routes (Phase 15 DB-backed)
# ---------------------------------------------------------------------------


def test_post_agent_run_returns_202(auth_headers: dict[str, str]) -> None:
    from fastapi.testclient import TestClient

    from api.dependencies import (
        get_execution_repository,
        get_reasoning_engine,
    )
    from api.main import create_app

    app = create_app()

    mock_repo = AsyncMock(spec=ExecutionRepository)
    mock_engine = AsyncMock()
    mock_engine.execute_goal = AsyncMock(
        return_value={"status": "SUCCESS", "metrics": None}
    )

    app.dependency_overrides[get_execution_repository] = lambda: mock_repo
    app.dependency_overrides[get_reasoning_engine] = lambda: mock_engine

    with TestClient(app) as client:
        mock_db = _make_db_manager_mock()
        with patch("api.routes.agent.db_manager", mock_db):
            response = client.post(
                "/api/v1/agent/run",
                json={"goal": "Solve problem X"},
                headers=auth_headers,
            )

    assert response.status_code == 202
    body = response.json()
    assert body["success"] is True
    assert "run_id" in body["data"]
    assert "trace_id" in body["data"]

    app.dependency_overrides.clear()


def test_get_agent_run_status_found(auth_headers: dict[str, str]) -> None:
    from fastapi.testclient import TestClient

    from api.dependencies import get_db_session, get_execution_repository
    from api.main import create_app

    app = create_app()

    run_id = uuid.uuid4()
    mock_model = MagicMock()
    mock_model.id = run_id
    mock_model.state = "Planning"
    mock_model.metrics = None
    mock_model.failure_type = None

    mock_repo = AsyncMock(spec=ExecutionRepository)
    mock_repo.get_agent_run = AsyncMock(return_value=mock_model)

    mock_session = AsyncMock()

    async def override_session():  # type: ignore[no-untyped-def]
        yield mock_session

    app.dependency_overrides[get_execution_repository] = lambda: mock_repo
    app.dependency_overrides[get_db_session] = override_session

    with TestClient(app) as client:
        response = client.get(f"/api/v1/agent/runs/{run_id}", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["run_id"] == str(run_id)
    assert body["data"]["state"] == "Planning"

    app.dependency_overrides.clear()


def test_get_agent_run_status_not_found(auth_headers: dict[str, str]) -> None:
    from fastapi.testclient import TestClient

    from api.dependencies import get_db_session, get_execution_repository
    from api.main import create_app

    app = create_app()

    run_id = uuid.uuid4()
    mock_repo = AsyncMock(spec=ExecutionRepository)
    mock_repo.get_agent_run = AsyncMock(return_value=None)

    mock_session = AsyncMock()

    async def override_session():  # type: ignore[no-untyped-def]
        yield mock_session

    app.dependency_overrides[get_execution_repository] = lambda: mock_repo
    app.dependency_overrides[get_db_session] = override_session

    with TestClient(app) as client:
        response = client.get(f"/api/v1/agent/runs/{run_id}", headers=auth_headers)

    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "RUN_NOT_FOUND"

    app.dependency_overrides.clear()


def test_get_agent_runs_history(auth_headers: dict[str, str]) -> None:
    from fastapi.testclient import TestClient

    from api.dependencies import get_db_session, get_execution_repository
    from api.main import create_app

    app = create_app()

    run_id_1 = uuid.uuid4()
    run_id_2 = uuid.uuid4()
    mock_model_1 = MagicMock()
    mock_model_1.id = run_id_1
    mock_model_1.state = "Completed"
    mock_model_1.metrics = None
    mock_model_1.failure_type = None

    mock_model_2 = MagicMock()
    mock_model_2.id = run_id_2
    mock_model_2.state = "Failed"
    mock_model_2.metrics = None
    mock_model_2.failure_type = "PlannerFailure"

    mock_repo = AsyncMock(spec=ExecutionRepository)
    mock_repo.list_agent_runs = AsyncMock(return_value=[mock_model_1, mock_model_2])

    mock_session = AsyncMock()

    async def override_session():  # type: ignore[no-untyped-def]
        yield mock_session

    app.dependency_overrides[get_execution_repository] = lambda: mock_repo
    app.dependency_overrides[get_db_session] = override_session

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/agent/runs?limit=10&offset=0", headers=auth_headers
        )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert len(body["data"]["runs"]) == 2
    assert body["data"]["runs"][0]["state"] == "Completed"
    assert body["data"]["runs"][1]["failure_type"] == "PlannerFailure"

    app.dependency_overrides.clear()


def test_get_agent_runs_history_empty(auth_headers: dict[str, str]) -> None:
    from fastapi.testclient import TestClient

    from api.dependencies import get_db_session, get_execution_repository
    from api.main import create_app

    app = create_app()

    mock_repo = AsyncMock(spec=ExecutionRepository)
    mock_repo.list_agent_runs = AsyncMock(return_value=[])

    mock_session = AsyncMock()

    async def override_session():  # type: ignore[no-untyped-def]
        yield mock_session

    app.dependency_overrides[get_execution_repository] = lambda: mock_repo
    app.dependency_overrides[get_db_session] = override_session

    with TestClient(app) as client:
        response = client.get("/api/v1/agent/runs", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["runs"] == []

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 6. API Route Integration Tests — workflow routes (Phase 15 DB-backed status)
# ---------------------------------------------------------------------------


def test_get_workflow_status_with_execution_record(
    auth_headers: dict[str, str],
) -> None:
    from fastapi.testclient import TestClient

    from api.dependencies import (
        get_db_session,
        get_execution_repository,
        get_workflow_repository,
    )
    from api.main import create_app

    app = create_app()

    wf_id = uuid.uuid4()

    mock_plan = MagicMock()
    mock_wf_repo = AsyncMock()
    mock_wf_repo.get = AsyncMock(return_value=mock_plan)

    mock_exec = MagicMock()
    mock_exec.state = "COMPLETED"
    mock_exec.metrics = None
    mock_exec_repo = AsyncMock(spec=ExecutionRepository)
    mock_exec_repo.get_latest_workflow_execution = AsyncMock(return_value=mock_exec)

    mock_session = AsyncMock()

    async def override_session():  # type: ignore[no-untyped-def]
        yield mock_session

    app.dependency_overrides[get_workflow_repository] = lambda: mock_wf_repo
    app.dependency_overrides[get_execution_repository] = lambda: mock_exec_repo
    app.dependency_overrides[get_db_session] = override_session

    with TestClient(app) as client:
        response = client.get(f"/api/v1/workflows/{wf_id}", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["state"] == "COMPLETED"

    app.dependency_overrides.clear()


def test_get_workflow_status_no_execution_defaults_to_pending(
    auth_headers: dict[str, str],
) -> None:
    from fastapi.testclient import TestClient

    from api.dependencies import (
        get_db_session,
        get_execution_repository,
        get_workflow_repository,
    )
    from api.main import create_app

    app = create_app()

    wf_id = uuid.uuid4()

    mock_plan = MagicMock()
    mock_wf_repo = AsyncMock()
    mock_wf_repo.get = AsyncMock(return_value=mock_plan)

    mock_exec_repo = AsyncMock(spec=ExecutionRepository)
    mock_exec_repo.get_latest_workflow_execution = AsyncMock(return_value=None)

    mock_session = AsyncMock()

    async def override_session():  # type: ignore[no-untyped-def]
        yield mock_session

    app.dependency_overrides[get_workflow_repository] = lambda: mock_wf_repo
    app.dependency_overrides[get_execution_repository] = lambda: mock_exec_repo
    app.dependency_overrides[get_db_session] = override_session

    with TestClient(app) as client:
        response = client.get(f"/api/v1/workflows/{wf_id}", headers=auth_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["state"] == "PENDING"

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 7. Component Import and Instantiation Tests
# ---------------------------------------------------------------------------


def test_execution_repository_has_all_methods() -> None:
    repo = ExecutionRepository()
    assert repo is not None
    assert hasattr(repo, "save_agent_run")
    assert hasattr(repo, "get_agent_run")
    assert hasattr(repo, "list_agent_runs")
    assert hasattr(repo, "save_workflow_execution")
    assert hasattr(repo, "update_workflow_execution")
    assert hasattr(repo, "get_latest_workflow_execution")
    assert hasattr(repo, "save_step_execution")
    assert hasattr(repo, "get_step_executions")
    assert hasattr(repo, "get_active_agent_run_ids")
    assert hasattr(repo, "get_active_workflow_run_ids")


def test_persistence_service_importable() -> None:
    from core.reasoning.persistence_service import PersistenceService

    mock_repo = MagicMock(spec=ExecutionRepository)
    mock_bus = AsyncMock()
    service = PersistenceService(repository=mock_repo, event_bus=mock_bus)
    assert service is not None
    assert hasattr(service, "initialize")
    assert hasattr(service, "start")
    assert hasattr(service, "stop")
    assert hasattr(service, "shutdown")


def test_resume_manager_importable() -> None:
    from core.tools.resume_manager import ResumeManager

    mock_repo = MagicMock(spec=ExecutionRepository)
    mock_bus = AsyncMock()
    manager = ResumeManager(repository=mock_repo, event_bus=mock_bus)
    assert manager is not None
    assert hasattr(manager, "resume_all")


def test_active_run_id_context_variable() -> None:
    from core.reasoning.persistence_service import active_run_id

    assert active_run_id.get() is None

    run_id = uuid.uuid4()
    token = active_run_id.set(run_id)
    assert active_run_id.get() == run_id
    active_run_id.reset(token)
    assert active_run_id.get() is None


def test_dependency_provider_get_execution_repository() -> None:
    import api.dependencies
    from api.dependencies import get_execution_repository

    mock_kernel = MagicMock()
    mock_repo = MagicMock(spec=ExecutionRepository)
    mock_kernel.container.resolve.return_value = mock_repo

    old_kernel = api.dependencies._kernel
    api.dependencies._kernel = mock_kernel

    try:
        result = get_execution_repository(kernel=mock_kernel)
        assert result is mock_repo
        mock_kernel.container.resolve.assert_called_with(ExecutionRepository)
    finally:
        api.dependencies._kernel = old_kernel


@pytest.mark.asyncio
async def test_execution_repository_db_integration() -> None:
    from core.config import Settings
    from core.memory.database import db_manager
    from core.tools.execution_repository import ExecutionRepository

    settings = Settings()
    db_manager.init(settings, connection_url="sqlite+aiosqlite:///:memory:")

    repository = ExecutionRepository()

    async with db_manager.session() as session:
        async with session.begin():
            # 1. Create tables
            await repository.create_tables(session)

    # 2. Test saving and getting agent run
    run_id = uuid.uuid4()
    async with db_manager.session() as session:
        async with session.begin():
            await repository.save_agent_run(
                run_id=run_id,
                goal="Solve the math problem",
                budget=5.0,
                state="Planning",
                session=session,
            )

    async with db_manager.session() as session:
        async with session.begin():
            # Test update goal/budget/state via save_agent_run
            await repository.save_agent_run(
                run_id=run_id,
                goal="Solve the math problem",
                budget=5.0,
                state="Planning",
                session=session,
            )

            run = await repository.get_agent_run(run_id, session)
            assert run is not None
            assert run.goal == "Solve the math problem"
            assert run.state == "Planning"
            assert run.budget == 5.0

    # 3. Test listing and active agent runs
    async with db_manager.session() as session:
        async with session.begin():
            active_runs = await repository.get_active_agent_run_ids(session)
            assert run_id in active_runs

            # List runs
            runs = await repository.list_agent_runs(10, 0, session)
            assert len(runs) >= 1
            assert runs[0].id == run_id

    # 4. Test updating agent run state
    async with db_manager.session() as session:
        async with session.begin():
            await repository.update_agent_run_state(
                run_id=run_id,
                state="Completed",
                session=session,
                metrics={"total_steps": 3},
            )

    async with db_manager.session() as session:
        async with session.begin():
            run = await repository.get_agent_run(run_id, session)
            assert run is not None
            assert run.state == "Completed"
            assert run.metrics == {"total_steps": 3}

            active_runs_after = await repository.get_active_agent_run_ids(session)
            assert run_id not in active_runs_after

    # 5. Test workflow executions
    exec_id = uuid.uuid4()
    wf_id = uuid.uuid4()
    async with db_manager.session() as session:
        async with session.begin():
            await repository.save_workflow_execution(
                execution_id=exec_id,
                workflow_id=wf_id,
                version=1,
                state="RUNNING",
                session=session,
            )

    async with db_manager.session() as session:
        async with session.begin():
            # Test update workflow execution via save
            await repository.save_workflow_execution(
                execution_id=exec_id,
                workflow_id=wf_id,
                version=1,
                state="RUNNING",
                session=session,
            )

            wf_exec = await repository.get_workflow_execution(exec_id, session)
            assert wf_exec is not None
            assert wf_exec.state == "RUNNING"

            latest_exec = await repository.get_latest_workflow_execution(wf_id, session)
            assert latest_exec is not None
            assert latest_exec.id == exec_id

            active_wfs = await repository.get_active_workflow_run_ids(session)
            assert exec_id in active_wfs

    # 6. Test updating workflow execution
    async with db_manager.session() as session:
        async with session.begin():
            await repository.update_workflow_execution(
                execution_id=exec_id,
                state="COMPLETED",
                session=session,
                metrics={"duration": 10.5},
            )

    async with db_manager.session() as session:
        async with session.begin():
            wf_exec = await repository.get_workflow_execution(exec_id, session)
            assert wf_exec is not None
            assert wf_exec.state == "COMPLETED"
            assert wf_exec.metrics == {"duration": 10.5}

            active_wfs_after = await repository.get_active_workflow_run_ids(session)
            assert exec_id not in active_wfs_after

    # 7. Test step executions
    async with db_manager.session() as session:
        async with session.begin():
            await repository.save_step_execution(
                execution_id=exec_id,
                step_name="step_a",
                state="RUNNING",
                attempts=1,
                session=session,
            )

    async with db_manager.session() as session:
        async with session.begin():
            steps = await repository.get_step_executions(exec_id, session)
            assert len(steps) == 1
            assert steps[0].step_name == "step_a"
            assert steps[0].state == "RUNNING"

            await repository.save_step_execution(
                execution_id=exec_id,
                step_name="step_a",
                state="COMPLETED",
                attempts=1,
                output={"key": "val"},
                session=session,
            )

    async with db_manager.session() as session:
        async with session.begin():
            steps = await repository.get_step_executions(exec_id, session)
            assert steps[0].state == "COMPLETED"
            assert steps[0].output == {"key": "val"}

    await db_manager.close()
