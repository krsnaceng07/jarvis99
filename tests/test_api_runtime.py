"""
PHASE: 23
STATUS: TEST
SPECIFICATION:
    docs/82_PHASE_22_ORCHESTRATOR_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/fa98328c-ff31-452a-9668-808df53aa5a3/implementation_plan.md

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest

from core.reasoning.task import ExecutorType, Task, TaskType
from core.tools.api_runtime import ApiRuntime


@pytest.mark.asyncio
async def test_api_runtime_get_success() -> None:
    runtime = ApiRuntime()
    dummy_req = httpx.Request("GET", "https://api.example.com/v1/health")
    mock_resp = httpx.Response(
        status_code=200,
        json={"status": "ok", "message": "success"},
        headers={"Content-Type": "application/json"},
        request=dummy_req,
    )

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.__aenter__.return_value = mock_client
    mock_client.request.return_value = mock_resp

    task = Task(
        id=uuid4(),
        goal_id=uuid4(),
        executor=ExecutorType.API,
        task_type=TaskType.API,
        payload={
            "method": "GET",
            "url": "https://api.example.com/v1/health",
        },
    )

    with patch("httpx.AsyncClient", return_value=mock_client):
        res = await runtime.execute(task, {})

    assert res.status == "SUCCESS"
    assert res.exit_code == 0
    assert res.artifacts["status_code"] == 200
    assert res.artifacts["json"] == {"status": "ok", "message": "success"}


@pytest.mark.asyncio
async def test_api_runtime_post_success() -> None:
    runtime = ApiRuntime()
    dummy_req = httpx.Request("POST", "https://api.example.com/v1/users")
    mock_resp = httpx.Response(
        status_code=201,
        json={"id": "123", "created": True},
        headers={"Content-Type": "application/json"},
        request=dummy_req,
    )

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.__aenter__.return_value = mock_client
    mock_client.request.return_value = mock_resp

    task = Task(
        id=uuid4(),
        goal_id=uuid4(),
        executor=ExecutorType.API,
        task_type=TaskType.API,
        payload={
            "method": "POST",
            "url": "https://api.example.com/v1/users",
            "json": {"username": "jarvis"},
        },
    )

    with patch("httpx.AsyncClient", return_value=mock_client):
        res = await runtime.execute(task, {})

    assert res.status == "SUCCESS"
    assert res.exit_code == 0
    assert res.artifacts["status_code"] == 201
    assert res.artifacts["json"] == {"id": "123", "created": True}


@pytest.mark.asyncio
async def test_api_runtime_retry_on_failure() -> None:
    runtime = ApiRuntime()
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.__aenter__.return_value = mock_client

    # Fail twice with RequestError, then succeed
    dummy_req = httpx.Request("GET", "https://api.example.com/v1/retry")
    mock_resp = httpx.Response(
        status_code=200,
        text="Success on third try",
        headers={"Content-Type": "text/plain"},
        request=dummy_req,
    )

    mock_client.request.side_effect = [
        httpx.RequestError("Network error 1"),
        httpx.RequestError("Network error 2"),
        mock_resp,
    ]

    task = Task(
        id=uuid4(),
        goal_id=uuid4(),
        executor=ExecutorType.API,
        task_type=TaskType.API,
        payload={
            "method": "GET",
            "url": "https://api.example.com/v1/retry",
            "max_retries": 3,
            "backoff_factor": 0.01,  # Short backoff for tests
        },
    )

    # Patch sleep to make tests fast
    with (
        patch("httpx.AsyncClient", return_value=mock_client),
        patch("asyncio.sleep", AsyncMock()),
    ):
        res = await runtime.execute(task, {})

    assert res.status == "SUCCESS"
    assert res.exit_code == 0
    assert res.stdout == "Success on third try"
    assert mock_client.request.call_count == 3
