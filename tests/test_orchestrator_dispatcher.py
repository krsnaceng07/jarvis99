"""
PHASE: 22
STATUS: TEST
SPECIFICATION:
    docs/82_PHASE_22_ORCHESTRATOR_SPECIFICATION.md

IMPLEMENTATION PLAN:
    LOCKED (Phase 22 Approved Plan)

AUTHORITATIVE:
    NO

DO NOT CHANGE CONTRACTS HERE.
Contracts come only from Phase Specification.
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest

from core.reasoning.dispatcher import ToolDispatcher
from core.reasoning.task import ExecutorType, Task, TaskStatus, TaskType


@pytest.mark.asyncio
async def test_tool_dispatcher_python() -> None:
    dispatcher = ToolDispatcher()
    task = Task(
        id=uuid4(),
        goal_id=uuid4(),
        task_type=TaskType.CODE,
        executor=ExecutorType.PYTHON,
        payload={"code": "print(2 + 2)"},
        status=TaskStatus.PENDING,
    )
    res = await dispatcher.dispatch(task, {})
    assert res.status == "SUCCESS"
    assert res.stdout.strip() == "4"
    assert res.exit_code == 0


@pytest.mark.asyncio
async def test_tool_dispatcher_python_failure() -> None:
    dispatcher = ToolDispatcher()
    task = Task(
        id=uuid4(),
        goal_id=uuid4(),
        task_type=TaskType.CODE,
        executor=ExecutorType.PYTHON,
        payload={"code": "raise RuntimeError('fail')"},
        status=TaskStatus.PENDING,
    )
    res = await dispatcher.dispatch(task, {})
    assert res.status == "FAILURE"
    assert res.exit_code == 1
    assert res.error is not None


@pytest.mark.asyncio
async def test_tool_dispatcher_shell() -> None:
    dispatcher = ToolDispatcher()
    task = Task(
        id=uuid4(),
        goal_id=uuid4(),
        task_type=TaskType.COMMAND,
        executor=ExecutorType.SHELL,
        payload={"command": "echo hello"},
        status=TaskStatus.PENDING,
    )
    res = await dispatcher.dispatch(task, {})
    assert res.status == "SUCCESS"
    assert "hello" in res.stdout.strip()


@pytest.mark.asyncio
async def test_tool_dispatcher_browser() -> None:
    dispatcher = ToolDispatcher()
    task = Task(
        id=uuid4(),
        goal_id=uuid4(),
        task_type=TaskType.SEARCH,
        executor=ExecutorType.BROWSER,
        payload={"url": "https://google.com"},
        status=TaskStatus.PENDING,
    )
    res = await dispatcher.dispatch(task, {})
    assert res.status == "SUCCESS"
    assert "google" in res.stdout.lower()


@pytest.mark.asyncio
async def test_tool_dispatcher_memory() -> None:
    dispatcher = ToolDispatcher()
    task = Task(
        id=uuid4(),
        goal_id=uuid4(),
        task_type=TaskType.MEMORY,
        executor=ExecutorType.MEMORY,
        payload={"query": "JARVIS"},
        status=TaskStatus.PENDING,
    )
    res = await dispatcher.dispatch(task, {})
    assert res.status == "SUCCESS"
    assert "Memory search query" in res.stdout


@pytest.mark.asyncio
async def test_tool_dispatcher_human() -> None:
    dispatcher = ToolDispatcher()
    task = Task(
        id=uuid4(),
        goal_id=uuid4(),
        task_type=TaskType.HUMAN,
        executor=ExecutorType.HUMAN,
        payload={"prompt": "Deploy to prod?", "auto_approve": True},
        status=TaskStatus.PENDING,
    )
    res = await dispatcher.dispatch(task, {})
    assert res.status == "SUCCESS"
    assert "approved" in res.stdout.lower()


@pytest.mark.asyncio
async def test_tool_dispatcher_llm() -> None:
    dispatcher = ToolDispatcher()
    task = Task(
        id=uuid4(),
        goal_id=uuid4(),
        task_type=TaskType.SYSTEM,
        executor=ExecutorType.LLM,
        payload={"prompt": "Write email copy"},
        status=TaskStatus.PENDING,
    )
    res = await dispatcher.dispatch(task, {})
    assert res.status == "SUCCESS"
    assert "LLM generated response" in res.stdout


@pytest.mark.asyncio
async def test_tool_dispatcher_api() -> None:
    dispatcher = ToolDispatcher()
    task = Task(
        id=uuid4(),
        goal_id=uuid4(),
        task_type=TaskType.API,
        executor=ExecutorType.API,
        payload={"endpoint": "https://api.example.com/weather"},
        status=TaskStatus.PENDING,
    )

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.__aenter__.return_value = mock_client
    dummy_req = httpx.Request("GET", "https://api.example.com/weather")
    mock_client.request.return_value = httpx.Response(
        status_code=200, json={"weather": "sunny"}, request=dummy_req
    )

    with patch("httpx.AsyncClient", return_value=mock_client):
        res = await dispatcher.dispatch(task, {})

    assert res.status == "SUCCESS"
    assert "sunny" in res.stdout
