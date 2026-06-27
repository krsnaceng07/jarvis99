"""JARVIS OS - Event Bus Subsystem Unit Tests.

Verifies MemoryEventBus local queue pub/sub, RedisEventBus streaming, and callback safety.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.events import MemoryEventBus, RedisEventBus, create_event_bus
from core.exceptions import JarvisSystemError
from core.interfaces import InterAgentMessage


@pytest.mark.asyncio
async def test_memory_event_bus_pub_sub() -> None:
    """Verify MemoryEventBus subscription and publishing flow."""
    bus = create_event_bus("development")
    assert isinstance(bus, MemoryEventBus)

    await bus.initialize()
    await bus.start()

    received_messages = []

    async def callback(msg: InterAgentMessage) -> None:
        received_messages.append(msg)

    sub_id = await bus.subscribe("agent.task.started", callback)
    assert sub_id is not None

    test_msg = InterAgentMessage(
        sender="Planner",
        receiver="Developer",
        action="test_action",
        body={"key": "val"},
    )

    publish_ok = await bus.publish("agent.task.started", test_msg)
    assert publish_ok

    # Yield control to allow background dispatch task to execute callback
    await asyncio.sleep(0.05)

    assert len(received_messages) == 1
    assert received_messages[0].action == "test_action"

    # Test unsubscribe
    unsub_ok = await bus.unsubscribe("agent.task.started", sub_id)
    assert unsub_ok

    publish_ok2 = await bus.publish("agent.task.started", test_msg)
    assert publish_ok2
    await asyncio.sleep(0.05)
    assert len(received_messages) == 1  # No new message

    await bus.stop()
    await bus.shutdown()


@pytest.mark.asyncio
async def test_memory_event_bus_inactive_drops() -> None:
    """Verify MemoryEventBus drops messages if not active."""
    bus = MemoryEventBus()
    await bus.initialize()
    # Not started

    test_msg = InterAgentMessage(
        sender="Planner",
        receiver="Developer",
        action="test_action",
        body={},
    )
    publish_ok = await bus.publish("test.topic", test_msg)
    assert not publish_ok


@pytest.mark.asyncio
async def test_redis_event_bus_connection_fail() -> None:
    """Verify RedisEventBus raises JarvisSystemError if connection fails."""
    bus = RedisEventBus(host="invalid-host-name-xyz", port=1234)
    with pytest.raises(JarvisSystemError) as exc_info:
        await bus.initialize()
    assert exc_info.value.code == "SYSTEM_001"
    assert "Redis connection failed" in exc_info.value.message


@pytest.mark.asyncio
@patch("redis.asyncio.Redis")
async def test_redis_event_bus_mock_pub_sub(mock_redis_class: MagicMock) -> None:
    """Verify RedisEventBus pub/sub interface using mocked Redis client."""
    mock_client = MagicMock()
    mock_client.ping = AsyncMock(return_value=True)
    mock_client.xadd = AsyncMock(return_value="123-0")
    mock_client.close = AsyncMock()
    mock_redis_class.return_value = mock_client

    bus = RedisEventBus(host="localhost", port=6379)
    await bus.initialize()
    await bus.start()

    test_msg = InterAgentMessage(
        sender="Planner",
        receiver="Developer",
        action="test_action",
        body={"foo": "bar"},
    )

    # Publish
    pub_ok = await bus.publish("agent.task.started", test_msg)
    assert pub_ok
    mock_client.xadd.assert_called_once()

    await bus.stop()
    await bus.shutdown()
    mock_client.close.assert_called_once()


@pytest.mark.asyncio
@patch("redis.asyncio.Redis")
async def test_redis_event_bus_failures_and_polling(
    mock_redis_class: MagicMock,
) -> None:
    """Verify RedisEventBus handles publishing failures and polls streams correctly."""
    mock_client = MagicMock()
    mock_client.ping = AsyncMock(return_value=True)
    # Simulate xadd raising exception
    mock_client.xadd = AsyncMock(side_effect=RuntimeError("Redis write error"))

    test_msg = InterAgentMessage(
        sender="Planner",
        receiver="Developer",
        action="test_action",
        body={},
    )

    # Mock xread to return a valid message on first call, then empty/block
    msg_json = test_msg.model_dump_json()
    # xread returns: [ (stream_name, [ (msg_id, {field: value}) ]) ]
    mock_client.xread = AsyncMock(
        side_effect=[
            [("agent.task.started", [("123-0", {"payload": msg_json})])],
            None,  # Subsequent poll blocks/returns None
        ]
    )
    mock_client.close = AsyncMock()
    mock_redis_class.return_value = mock_client

    bus = RedisEventBus(host="localhost", port=6379)
    await bus.initialize()
    await bus.start()

    # 1. Verify publishing exceptions raise JarvisSystemError
    with pytest.raises(JarvisSystemError) as exc_info:
        await bus.publish("agent.task.started", test_msg)
    assert exc_info.value.code == "SYSTEM_999"

    # 2. Verify subscription and loop polling
    received_msgs = []

    async def callback(msg: InterAgentMessage) -> None:
        received_msgs.append(msg)

    sub_id = await bus.subscribe("agent.task.started", callback)
    assert sub_id is not None

    # Wait for the background loop to trigger the side_effect sequence
    await asyncio.sleep(0.15)
    assert len(received_msgs) == 1
    assert received_msgs[0].action == "test_action"

    # 3. Verify unsubscribe
    unsub_ok = await bus.unsubscribe("agent.task.started", sub_id)
    assert unsub_ok

    await bus.stop()
    await bus.shutdown()
