"""
PHASE: 14
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/76_PHASE_14_API_GATEWAY_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/721908f6-e992-4e3d-9eca-2fca584e321e/implementation_plan.md

AUTHORITATIVE:
    NO
"""

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from api.dto import (
    AgentRunAcceptedResponse,
    AgentRunRequest,
    AgentRunStatusResponse,
    ErrorDetail,
    ErrorEnvelope,
    HealthResponse,
    SessionState,
    SuccessEnvelope,
    WorkflowState,
    WorkflowStatusResponse,
    WorkflowSubmitRequest,
    WorkflowSubmitResponse,
)


def test_agent_run_request_validation() -> None:
    # Valid goal and default budget
    req = AgentRunRequest(goal="Solve this puzzle")
    assert req.goal == "Solve this puzzle"
    assert req.budget == 10.0

    # Invalid goal (empty)
    with pytest.raises(ValidationError):
        AgentRunRequest(goal="")

    # Goal too long
    with pytest.raises(ValidationError):
        AgentRunRequest(goal="a" * 4001)

    # Budget out of range (lower bound)
    with pytest.raises(ValidationError):
        AgentRunRequest(goal="Goal", budget=-1.0)

    # Budget out of range (upper bound)
    with pytest.raises(ValidationError):
        AgentRunRequest(goal="Goal", budget=1001.0)


def test_workflow_submit_request_validation() -> None:
    # Valid submission
    req = WorkflowSubmitRequest(name="Plan A", steps=[])
    assert req.name == "Plan A"
    assert req.steps == []
    assert req.version == 1

    # Empty name
    with pytest.raises(ValidationError):
        WorkflowSubmitRequest(name="", steps=[])


def test_agent_run_accepted_response() -> None:
    run_id = uuid.uuid4()
    trace_id = uuid.uuid4()
    resp = AgentRunAcceptedResponse(run_id=run_id, trace_id=trace_id)
    assert resp.run_id == run_id
    assert resp.trace_id == trace_id
    assert resp.status == "accepted"
    assert resp.api_version == "v1"


def test_agent_run_status_response() -> None:
    run_id = uuid.uuid4()
    resp = AgentRunStatusResponse(run_id=run_id, state=SessionState.PLANNING)
    assert resp.run_id == run_id
    assert resp.state == SessionState.PLANNING
    assert resp.metrics is None
    assert resp.failure_type is None
    assert resp.api_version == "v1"


def test_workflow_submit_response() -> None:
    wf_id = uuid.uuid4()
    resp = WorkflowSubmitResponse(workflow_id=wf_id, version=1)
    assert resp.workflow_id == wf_id
    assert resp.version == 1
    assert resp.status == WorkflowState.PENDING
    assert resp.api_version == "v1"


def test_workflow_status_response() -> None:
    wf_id = uuid.uuid4()
    resp = WorkflowStatusResponse(workflow_id=wf_id, state=WorkflowState.RUNNING)
    assert resp.workflow_id == wf_id
    assert resp.state == WorkflowState.RUNNING
    assert resp.metrics is None
    assert resp.api_version == "v1"


def test_health_response() -> None:
    resp = HealthResponse(status="healthy", uptime_seconds=120.5)
    assert resp.status == "healthy"
    assert resp.uptime_seconds == 120.5
    assert resp.phase == "Phase 14"
    assert resp.api_version == "v1"


def test_error_detail() -> None:
    err = ErrorDetail(code="SYSTEM_999", message="System failure")
    assert err.code == "SYSTEM_999"
    assert err.message == "System failure"
    assert err.details == {}
    assert err.api_version == "v1"


def test_envelopes_validation() -> None:
    run_id = uuid.uuid4()
    trace_id = uuid.uuid4()
    data_payload = AgentRunAcceptedResponse(run_id=run_id, trace_id=trace_id)

    # Success envelope
    envelope = SuccessEnvelope[AgentRunAcceptedResponse](data=data_payload)
    assert envelope.success is True
    assert envelope.data.run_id == run_id
    assert isinstance(envelope.meta.timestamp, datetime)
    assert isinstance(envelope.meta.request_id, uuid.UUID)

    # Error envelope
    err_detail = ErrorDetail(code="AGENT_001", message="Run failed")
    err_envelope = ErrorEnvelope(error=err_detail)
    assert err_envelope.success is False
    assert err_envelope.error.code == "AGENT_001"
    assert isinstance(err_envelope.meta.timestamp, datetime)
    assert isinstance(err_envelope.meta.request_id, uuid.UUID)


def test_api_dependencies_fail_fast() -> None:
    import api.dependencies

    api.dependencies._kernel = None

    from core.exceptions import JarvisSystemError

    with pytest.raises(JarvisSystemError) as exc:
        api.dependencies._require_kernel()
    assert exc.value.code == "SYSTEM_001"


def test_api_dependencies_successful_resolutions() -> None:
    from unittest.mock import MagicMock

    from api.dependencies import (
        get_agent_runs,
        get_event_bus,
        get_health_monitor,
        get_kernel,
        get_reasoning_engine,
        get_settings,
        get_tool_runtime,
        get_workflow_orchestrator,
        get_workflow_repository,
        get_workflow_validator,
        set_kernel,
    )
    from core.kernel import Kernel

    mock_kernel = MagicMock(spec=Kernel)
    mock_container = MagicMock()
    mock_kernel.container = mock_container

    # Bind kernel
    set_kernel(mock_kernel)
    assert get_kernel() is mock_kernel

    # Verify set_kernel twice with same kernel passes silently
    set_kernel(mock_kernel)

    # Verify set_kernel twice with different kernel raises RuntimeError
    another_mock = MagicMock(spec=Kernel)
    with pytest.raises(RuntimeError):
        set_kernel(another_mock)

    # Mock container resolutions
    mock_container.resolve.side_effect = lambda cls: f"resolved_{cls.__name__}"

    assert get_settings(mock_kernel) == "resolved_Settings"
    assert get_event_bus(mock_kernel) == "resolved_EventBusInterface"
    assert get_health_monitor(mock_kernel) == "resolved_HealthMonitor"
    assert get_tool_runtime(mock_kernel) == "resolved_ToolRuntime"
    assert get_reasoning_engine(mock_kernel) == "resolved_ReasoningExecutionEngine"
    assert get_workflow_validator(mock_kernel) == "resolved_WorkflowValidator"
    assert get_workflow_repository(mock_kernel) == "resolved_WorkflowRepository"
    assert get_workflow_orchestrator(mock_kernel) == "resolved_WorkflowOrchestrator"

    # Verify get_agent_runs
    runs = get_agent_runs()
    assert isinstance(runs, dict)


def test_map_exception_validation_error() -> None:
    import uuid

    from fastapi.exceptions import RequestValidationError

    from api.middleware import map_exception_to_envelope

    req_id = uuid.uuid4()
    exc = RequestValidationError(
        errors=[
            {
                "loc": ("body", "goal"),
                "msg": "field required",
                "type": "value_error.missing",
            }
        ]
    )
    status, env = map_exception_to_envelope(exc, req_id)
    assert status == 422
    assert env.success is False
    assert env.error.code == "VALIDATION_ERROR"
    assert "errors" in env.error.details


def test_map_exception_jarvis_errors() -> None:
    import uuid

    from api.middleware import map_exception_to_envelope
    from core.exceptions import (
        AuthenticationError,
        BudgetExceededError,
        JarvisAgentError,
        JarvisMemoryError,
        JarvisSkillError,
        JarvisSystemError,
        RateLimitError,
        TimeoutError,
    )

    req_id = uuid.uuid4()

    # Test sanitization
    details = {
        "ok_field": "visible",
        "credential": "secret_password",
        "stack_trace": "some trace",
    }

    exc = JarvisMemoryError("MEMORY_001", "Out of memory", details)
    status, env = map_exception_to_envelope(exc, req_id)
    assert status == 503
    assert env.error.code == "MEMORY_001"
    assert env.error.details["ok_field"] == "visible"
    assert "credential" not in env.error.details
    assert "stack_trace" not in env.error.details

    # Test status code mappings
    assert (
        map_exception_to_envelope(JarvisSystemError("SYS_001", "Sys error"), req_id)[0]
        == 500
    )
    assert (
        map_exception_to_envelope(JarvisAgentError("AGN_001", "Agent error"), req_id)[0]
        == 422
    )
    assert (
        map_exception_to_envelope(JarvisSkillError("SKL_001", "Skill error"), req_id)[0]
        == 500
    )
    assert (
        map_exception_to_envelope(
            BudgetExceededError("MOD_001", "Budget error"), req_id
        )[0]
        == 402
    )
    assert (
        map_exception_to_envelope(RateLimitError("MOD_002", "Rate error"), req_id)[0]
        == 429
    )
    assert (
        map_exception_to_envelope(AuthenticationError("MOD_003", "Auth error"), req_id)[
            0
        ]
        == 401
    )
    assert (
        map_exception_to_envelope(TimeoutError("MOD_004", "Timeout error"), req_id)[0]
        == 504
    )


@pytest.mark.asyncio
async def test_request_state_middleware_dispatch_success() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import Request, Response

    from api.middleware import RequestStateMiddleware

    middleware = RequestStateMiddleware(app=MagicMock())
    request = MagicMock(spec=Request)
    request.state = MagicMock()

    mock_response = MagicMock(spec=Response)
    mock_response.headers = {}

    call_next = AsyncMock(return_value=mock_response)

    result = await middleware.dispatch(request, call_next)

    assert result is mock_response
    assert "X-Request-ID" in result.headers
    assert "X-Response-Time" in result.headers
    assert isinstance(request.state.request_id, uuid.UUID)


@pytest.mark.asyncio
async def test_request_state_middleware_dispatch_error() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import Request

    from api.middleware import RequestStateMiddleware

    middleware = RequestStateMiddleware(app=MagicMock())
    request = MagicMock(spec=Request)
    request.state = MagicMock()

    call_next = AsyncMock(side_effect=ValueError("Unhandled raw error"))

    result = await middleware.dispatch(request, call_next)

    assert result.status_code == 500
    assert "X-Request-ID" in result.headers


def test_register_exception_handlers() -> None:
    import asyncio
    from unittest.mock import MagicMock

    from fastapi import FastAPI
    from fastapi.exceptions import RequestValidationError

    from api.middleware import register_exception_handlers
    from core.exceptions import JarvisError

    app = FastAPI()
    register_exception_handlers(app)

    assert Exception in app.exception_handlers
    assert RequestValidationError in app.exception_handlers
    assert JarvisError in app.exception_handlers

    # Call handlers directly to ensure execution coverage
    request = MagicMock()
    request.state = MagicMock()
    request.state.request_id = uuid.uuid4()

    handler_val = app.exception_handlers[RequestValidationError]
    res_val = asyncio.run(handler_val(request, RequestValidationError(errors=[])))
    assert res_val.status_code == 422

    handler_jarvis = app.exception_handlers[JarvisError]
    res_jarvis = asyncio.run(
        handler_jarvis(request, JarvisError("TEST_001", "Jarvis err"))
    )
    assert res_jarvis.status_code == 500

    handler_exc = app.exception_handlers[Exception]
    res_exc = asyncio.run(handler_exc(request, ValueError("Raw err")))
    assert res_exc.status_code == 500


@pytest.mark.asyncio
async def test_health_route_healthy() -> None:
    import json
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import Request

    from api.routes.health import health
    from core.health import HealthMonitor

    mock_monitor = MagicMock(spec=HealthMonitor)
    mock_monitor.check_health = AsyncMock(
        return_value={"status": "healthy", "uptime_seconds": 3600.0}
    )

    request = MagicMock(spec=Request)
    request.state = MagicMock()
    request.state.request_id = uuid.uuid4()

    response = await health(request, mock_monitor)
    assert response.status_code == 200

    body = json.loads(response.body)
    assert body["success"] is True
    assert body["data"]["status"] == "healthy"
    assert body["data"]["uptime_seconds"] == 3600.0


@pytest.mark.asyncio
async def test_health_route_degraded() -> None:
    import json
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import Request

    from api.routes.health import health
    from core.health import HealthMonitor

    mock_monitor = MagicMock(spec=HealthMonitor)
    mock_monitor.check_health = AsyncMock(
        return_value={"status": "degraded", "uptime_seconds": 120.0}
    )

    request = MagicMock(spec=Request)
    request.state = MagicMock()
    request.state.request_id = None

    response = await health(request, mock_monitor)
    assert response.status_code == 503

    body = json.loads(response.body)
    assert body["success"] is True
    assert body["data"]["status"] == "degraded"
    assert body["data"]["uptime_seconds"] == 120.0


@pytest.mark.asyncio
async def test_run_agent_route_post_success(mock_request_context) -> None:
    import json
    from unittest.mock import AsyncMock, MagicMock, patch

    from fastapi import BackgroundTasks, Request

    from api.dto import AgentRunRequest
    from api.routes.agent import run_agent
    from core.reasoning.engine import ReasoningExecutionEngine
    from core.tools.execution_repository import ExecutionRepository

    mock_engine = MagicMock(spec=ReasoningExecutionEngine)
    mock_repository = AsyncMock(spec=ExecutionRepository)

    request = MagicMock(spec=Request)
    request.state = MagicMock()
    request.state.request_id = None

    payload = AgentRunRequest(goal="Test goal", budget=15.0)
    bg_tasks = MagicMock(spec=BackgroundTasks)

    from tests.test_persistent_execution import _make_db_manager_mock

    mock_db = _make_db_manager_mock()
    with patch("api.routes.agent.db_manager", mock_db):
        response = await run_agent(
            request,
            payload,
            bg_tasks,
            mock_request_context,
            mock_engine,
            mock_repository,
        )

    assert response.status_code == 202

    body = json.loads(response.body)
    assert body["success"] is True
    assert "run_id" in body["data"]

    run_id = uuid.UUID(body["data"]["run_id"])
    mock_repository.save_agent_run.assert_called_once()
    call_kwargs = mock_repository.save_agent_run.call_args.kwargs
    assert call_kwargs["run_id"] == run_id
    assert call_kwargs["goal"] == "Test goal"
    assert call_kwargs["budget"] == 15.0
    assert call_kwargs["state"] == "Planning"
    bg_tasks.add_task.assert_called_once()


@pytest.mark.asyncio
async def test_run_agent_in_background_lifecycle() -> None:
    from unittest.mock import AsyncMock, patch

    from api.routes.agent import run_agent_in_background
    from core.reasoning.engine import ReasoningExecutionEngine
    from core.tools.execution_repository import ExecutionRepository
    from tests.test_persistent_execution import _make_db_manager_mock

    # 1. Test success path
    mock_engine = AsyncMock(spec=ReasoningExecutionEngine)
    mock_engine.execute_goal.return_value = {
        "status": "SUCCESS",
        "metrics": {"total_cost": 0.05, "total_steps": 3, "wall_time_seconds": 1.2},
    }
    mock_repo = AsyncMock(spec=ExecutionRepository)

    run_id = uuid.uuid4()
    mock_db = _make_db_manager_mock()

    with patch("api.routes.agent.db_manager", mock_db):
        await run_agent_in_background(run_id, "Goal", 10.0, mock_engine, mock_repo)

    assert mock_repo.update_agent_run_state.call_count == 2

    call_1 = mock_repo.update_agent_run_state.call_args_list[0].kwargs
    assert call_1["run_id"] == run_id
    assert call_1["state"] == "Executing"

    call_2 = mock_repo.update_agent_run_state.call_args_list[1].kwargs
    assert call_2["run_id"] == run_id
    assert call_2["state"] == "Completed"
    from api.dto import EngineMetrics

    expected_metrics = EngineMetrics(
        total_cost=0.05, total_steps=3, wall_time_seconds=1.2
    ).model_dump(mode="json")
    assert call_2["metrics"] == expected_metrics
    assert call_2["failure_type"] is None

    # 2. Test failure path with failure type
    mock_engine.execute_goal.return_value = {
        "status": "FAILURE",
        "failure_type": "ModelFailure",
    }
    mock_repo = AsyncMock(spec=ExecutionRepository)
    with patch("api.routes.agent.db_manager", mock_db):
        await run_agent_in_background(run_id, "Goal", 10.0, mock_engine, mock_repo)
    assert mock_repo.update_agent_run_state.call_count == 2
    call_failure = mock_repo.update_agent_run_state.call_args_list[1].kwargs
    assert call_failure["state"] == "Failed"
    assert call_failure["failure_type"] == "ModelFailure"

    # 3. Test failure path with invalid failure type (value error fallback)
    mock_engine.execute_goal.return_value = {
        "status": "FAILURE",
        "failure_type": "InvalidEnumVal",
    }
    mock_repo = AsyncMock(spec=ExecutionRepository)
    with patch("api.routes.agent.db_manager", mock_db):
        await run_agent_in_background(run_id, "Goal", 10.0, mock_engine, mock_repo)
    assert mock_repo.update_agent_run_state.call_count == 2
    call_fallback = mock_repo.update_agent_run_state.call_args_list[1].kwargs
    assert call_fallback["state"] == "Failed"
    assert call_fallback["failure_type"] == "PlannerFailure"

    # 4. Test exception path
    mock_engine.execute_goal.side_effect = ValueError("Core engine crashed")
    mock_repo = AsyncMock(spec=ExecutionRepository)
    with patch("api.routes.agent.db_manager", mock_db):
        await run_agent_in_background(run_id, "Goal", 10.0, mock_engine, mock_repo)
    assert mock_repo.update_agent_run_state.call_count == 2
    call_exception = mock_repo.update_agent_run_state.call_args_list[1].kwargs
    assert call_exception["state"] == "Failed"
    assert call_exception["failure_type"] == "PlannerFailure"


@pytest.mark.asyncio
async def test_get_run_status_route(mock_request_context) -> None:
    import json
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import Request

    from api.routes.agent import get_run_status
    from core.tools.execution_models import AgentRunModel
    from core.tools.execution_repository import ExecutionRepository

    run_id = uuid.uuid4()
    mock_model = AgentRunModel(
        id=run_id,
        goal="Test",
        budget=10.0,
        state="Completed",
    )
    mock_repo = AsyncMock(spec=ExecutionRepository)
    mock_repo.get_agent_run.return_value = mock_model

    request = MagicMock(spec=Request)
    request.state = MagicMock()
    request.state.request_id = uuid.uuid4()

    session = MagicMock()

    # 1. Success 200 path
    response = await get_run_status(
        request, run_id, mock_request_context, mock_repo, session
    )
    assert response.status_code == 200
    body = json.loads(response.body)
    assert body["success"] is True
    assert body["data"]["state"] == "Completed"

    # 2. Missing 404 path
    mock_repo.get_agent_run.return_value = None
    request.state.request_id = None
    missing_id = uuid.uuid4()
    response_missing = await get_run_status(
        request, missing_id, mock_request_context, mock_repo, session
    )
    assert response_missing.status_code == 404
    body_missing = json.loads(response_missing.body)
    assert body_missing["success"] is False
    assert body_missing["error"]["code"] == "RUN_NOT_FOUND"


@pytest.mark.asyncio
async def test_run_agent_route_post_with_request_id(mock_request_context) -> None:
    import json
    from unittest.mock import AsyncMock, MagicMock, patch

    from fastapi import BackgroundTasks, Request

    from api.dto import AgentRunRequest
    from api.routes.agent import run_agent
    from core.reasoning.engine import ReasoningExecutionEngine
    from core.tools.execution_repository import ExecutionRepository

    mock_engine = MagicMock(spec=ReasoningExecutionEngine)
    mock_repo = AsyncMock(spec=ExecutionRepository)

    request = MagicMock(spec=Request)
    request.state = MagicMock()
    request.state.request_id = uuid.uuid4()

    payload = AgentRunRequest(goal="Test goal", budget=15.0)
    bg_tasks = MagicMock(spec=BackgroundTasks)

    from tests.test_persistent_execution import _make_db_manager_mock

    mock_db = _make_db_manager_mock()
    with patch("api.routes.agent.db_manager", mock_db):
        response = await run_agent(
            request, payload, bg_tasks, mock_request_context, mock_engine, mock_repo
        )
    assert response.status_code == 202

    body = json.loads(response.body)
    assert body["success"] is True
    assert "run_id" in body["data"]


@pytest.mark.asyncio
async def test_submit_workflow_route_success(mock_request_context) -> None:
    import json
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import Request
    from sqlalchemy.ext.asyncio import AsyncSession

    from api.dto import WorkflowSubmitRequest
    from api.routes.workflow import submit_workflow
    from core.tools.repository import WorkflowRepository
    from core.tools.validator import WorkflowValidator
    from core.tools.workflow_dto import WorkflowVersion

    mock_validator = MagicMock(spec=WorkflowValidator)
    mock_repository = MagicMock(spec=WorkflowRepository)
    mock_session = MagicMock(spec=AsyncSession)

    workflow_id = uuid.uuid4()
    mock_repository.save = AsyncMock(
        return_value=WorkflowVersion(
            workflow_id=workflow_id,
            version=1,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            checksum="abc",
        )
    )

    request = MagicMock(spec=Request)
    request.state = MagicMock()
    request.state.request_id = uuid.uuid4()

    payload = WorkflowSubmitRequest(name="Plan B", steps=[])

    response = await submit_workflow(
        request,
        payload,
        mock_request_context,
        mock_validator,
        mock_repository,
        mock_session,
    )
    assert response.status_code == 202

    body = json.loads(response.body)
    assert body["success"] is True
    assert body["data"]["workflow_id"] == str(workflow_id)
    assert body["data"]["version"] == 1
    assert body["data"]["status"] == "PENDING"

    # Verify validator and compiler and save calls
    mock_validator.validate.assert_called_once()
    mock_repository.save.assert_called_once()


@pytest.mark.asyncio
async def test_submit_workflow_route_no_request_id(mock_request_context) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import Request
    from sqlalchemy.ext.asyncio import AsyncSession

    from api.dto import WorkflowSubmitRequest
    from api.routes.workflow import submit_workflow
    from core.tools.repository import WorkflowRepository
    from core.tools.validator import WorkflowValidator
    from core.tools.workflow_dto import WorkflowVersion

    mock_validator = MagicMock(spec=WorkflowValidator)
    mock_repository = MagicMock(spec=WorkflowRepository)
    mock_session = MagicMock(spec=AsyncSession)

    workflow_id = uuid.uuid4()
    mock_repository.save = AsyncMock(
        return_value=WorkflowVersion(
            workflow_id=workflow_id,
            version=1,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            checksum="abc",
        )
    )

    request = MagicMock(spec=Request)
    request.state = MagicMock()
    request.state.request_id = None

    payload = WorkflowSubmitRequest(name="Plan B", steps=[])

    response = await submit_workflow(
        request,
        payload,
        mock_request_context,
        mock_validator,
        mock_repository,
        mock_session,
    )
    assert response.status_code == 202


@pytest.mark.asyncio
async def test_get_workflow_status_route(mock_request_context) -> None:
    import json
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import Request
    from sqlalchemy.ext.asyncio import AsyncSession

    from api.routes.workflow import get_workflow_status
    from core.tools.execution_repository import ExecutionRepository
    from core.tools.repository import WorkflowRepository
    from core.tools.workflow_dto import WorkflowPlan

    mock_repository = MagicMock(spec=WorkflowRepository)
    mock_exec_repo = AsyncMock(spec=ExecutionRepository)
    mock_session = MagicMock(spec=AsyncSession)

    mock_exec_repo.get_latest_workflow_execution.return_value = None

    workflow_id = uuid.uuid4()
    mock_repository.get = AsyncMock(
        return_value=WorkflowPlan(name="Plan B", workflow_id=workflow_id, steps=[])
    )

    request = MagicMock(spec=Request)
    request.state = MagicMock()
    request.state.request_id = uuid.uuid4()

    # 1. Success 200 path
    response = await get_workflow_status(
        request,
        workflow_id,
        mock_request_context,
        mock_repository,
        mock_exec_repo,
        mock_session,
    )
    assert response.status_code == 200
    body = json.loads(response.body)
    assert body["success"] is True
    assert body["data"]["workflow_id"] == str(workflow_id)

    # 2. Missing 404 path with request_id = None
    mock_repository.get.return_value = None
    request.state.request_id = None
    response_missing = await get_workflow_status(
        request,
        workflow_id,
        mock_request_context,
        mock_repository,
        mock_exec_repo,
        mock_session,
    )
    assert response_missing.status_code == 404
    body_missing = json.loads(response_missing.body)
    assert body_missing["success"] is False
    assert body_missing["error"]["code"] == "WORKFLOW_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_db_session() -> None:
    from unittest.mock import AsyncMock, patch

    from api.dependencies import get_db_session

    mock_session = AsyncMock()
    with patch("api.dependencies.db_manager.session") as mock_session_ctx:
        mock_session_ctx.return_value.__aenter__.return_value = mock_session

        generator = get_db_session()
        session = await anext(generator)
        assert session is mock_session

        try:
            await anext(generator)
        except StopAsyncIteration:
            pass


@pytest.mark.asyncio
async def test_telemetry_hub_websocket_lifecycle() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import WebSocket, WebSocketDisconnect

    from api.stream_service import telemetry_hub
    from core.events.base import EventBus

    mock_ws = MagicMock(spec=WebSocket)
    mock_ws.accept = AsyncMock()
    mock_ws.send_json = AsyncMock()
    mock_ws.close = AsyncMock()

    run_id = uuid.uuid4()
    mock_ws.receive_json = AsyncMock(
        side_effect=[
            {"action": "subscribe", "run_id": str(run_id)},
            {"action": "unsubscribe", "run_id": str(run_id)},
            {"action": "subscribe", "run_id": str(run_id)},
            WebSocketDisconnect(),
        ]
    )

    mock_bus = MagicMock(spec=EventBus)
    mock_bus.subscribe = AsyncMock(return_value="sub_123")
    mock_bus.unsubscribe = AsyncMock(return_value=True)

    await telemetry_hub(mock_ws, mock_bus)

    mock_ws.accept.assert_called_once()
    assert mock_bus.subscribe.call_count > 0
    assert mock_bus.unsubscribe.call_count > 0


@pytest.mark.asyncio
async def test_telemetry_hub_event_broadcasting() -> None:
    import asyncio
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import WebSocket, WebSocketDisconnect

    from api.stream_service import telemetry_hub
    from core.events.base import EventBus
    from core.interfaces import InterAgentMessage

    mock_ws = MagicMock(spec=WebSocket)
    mock_ws.accept = AsyncMock()
    mock_ws.send_json = AsyncMock()
    mock_ws.close = AsyncMock()

    run_id = uuid.uuid4()
    mock_ws.receive_json = AsyncMock(
        side_effect=[
            {"action": "subscribe", "run_id": str(run_id)},
            WebSocketDisconnect(),
        ]
    )

    captured_callbacks = []

    async def mock_subscribe(topic: str, callback) -> str:
        captured_callbacks.append(callback)
        return "sub_id"

    mock_bus = MagicMock(spec=EventBus)
    mock_bus.subscribe = AsyncMock(side_effect=mock_subscribe)
    mock_bus.unsubscribe = AsyncMock()

    # Run the hub task in the background
    task = asyncio.create_task(telemetry_hub(mock_ws, mock_bus))

    # Yield control to let telemetry_hub execute and subscribe
    await asyncio.sleep(0.01)

    assert len(captured_callbacks) > 0
    callback = captured_callbacks[0]

    # 1. Trigger event with matching run_id
    msg_matching = InterAgentMessage(
        sender="engine",
        receiver="bus",
        action="transition",
        body={"run_id": str(run_id), "status": "active"},
    )
    await callback(msg_matching)

    # 1b. Trigger event with matching run_id but send_json failing
    mock_ws.send_json.side_effect = ValueError("Send failed")
    await callback(msg_matching)
    mock_ws.send_json.side_effect = None

    # 2. Trigger event with missing/invalid run_id
    msg_no_run_id = InterAgentMessage(
        sender="engine", receiver="bus", action="transition", body={}
    )
    await callback(msg_no_run_id)

    msg_invalid_run_id = InterAgentMessage(
        sender="engine",
        receiver="bus",
        action="transition",
        body={"run_id": "not-a-uuid"},
    )
    await callback(msg_invalid_run_id)

    # 3. Trigger event with different run_id
    msg_other_run_id = InterAgentMessage(
        sender="engine",
        receiver="bus",
        action="transition",
        body={"run_id": str(uuid.uuid4())},
    )
    await callback(msg_other_run_id)

    # Wait for the task to finish
    await task

    # Check that send_json was called for the matching run_id only (once success, once exception)
    assert mock_ws.send_json.call_count == 2
    sent_frame = mock_ws.send_json.call_args[0][0]
    assert sent_frame["event"] == "transition"
    assert sent_frame["payload"]["run_id"] == str(run_id)


@pytest.mark.asyncio
async def test_telemetry_hub_edge_cases() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from fastapi import WebSocket, WebSocketDisconnect

    from api.stream_service import telemetry_hub
    from core.events.base import EventBus

    mock_ws = MagicMock(spec=WebSocket)
    mock_ws.accept = AsyncMock()
    # 1. Invalid payload command, 2. Invalid UUID format, 3. Unsubscribe, 4. Disconnect
    mock_ws.receive_json = AsyncMock(
        side_effect=[
            {"action": "subscribe"},  # Missing run_id
            {"action": "subscribe", "run_id": "invalid-uuid"},  # Invalid UUID
            {
                "action": "unsubscribe",
                "run_id": str(uuid.uuid4()),
            },  # Unsubscribe action
            WebSocketDisconnect(),
        ]
    )
    mock_ws.close = AsyncMock(side_effect=ValueError("WebSocket close failed"))

    mock_bus = MagicMock(spec=EventBus)

    # Trigger exception in subscribe for one topic
    async def mock_subscribe(topic: str, callback) -> str:
        if topic == "system.kernel.ready":
            raise ValueError("Subscribe failed")
        return "sub_id"

    mock_bus.subscribe = AsyncMock(side_effect=mock_subscribe)
    # Trigger exception in unsubscribe
    mock_bus.unsubscribe = AsyncMock(side_effect=ValueError("Unsubscribe failed"))

    await telemetry_hub(mock_ws, mock_bus)

    mock_ws.accept.assert_called_once()
    mock_ws.close.assert_called_once()


@pytest.mark.asyncio
async def test_app_lifespan() -> None:
    from unittest.mock import AsyncMock, MagicMock, patch

    from fastapi import FastAPI

    from api.main import lifespan

    mock_kernel = AsyncMock()
    mock_kernel.container = MagicMock()
    mock_kernel.boot = AsyncMock(return_value=True)
    mock_kernel.lifecycle_manager.stop_all = AsyncMock()
    mock_kernel.lifecycle_manager.shutdown_all = AsyncMock()
    with (
        patch("api.main.Kernel", return_value=mock_kernel),
        patch("api.main.set_kernel") as mock_set_kernel,
    ):
        app = FastAPI()
        async with lifespan(app):
            pass

        mock_kernel.initialize.assert_called_once()
        mock_kernel.boot.assert_called_once()
        mock_set_kernel.assert_called_once_with(mock_kernel)
        mock_kernel.lifecycle_manager.stop_all.assert_called_once()
        mock_kernel.lifecycle_manager.shutdown_all.assert_called_once()
        mock_kernel.shutdown.assert_called_once()


def test_create_app() -> None:
    from unittest.mock import AsyncMock, MagicMock

    from fastapi.testclient import TestClient

    from api.dependencies import get_health_monitor
    from api.main import create_app

    app = create_app()

    mock_health = MagicMock()
    mock_health.check_health = AsyncMock(
        return_value={"status": "healthy", "uptime_seconds": 100.0}
    )
    app.dependency_overrides[get_health_monitor] = lambda: mock_health

    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == "healthy"
