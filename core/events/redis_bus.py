"""JARVIS OS - Redis Event Bus.

Production-grade event bus utilizing Redis Streams for asynchronous message routing.
"""

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional, Set
from uuid import uuid4

import redis.asyncio as aioredis

from core.events.base import EventBus
from core.exceptions import JarvisSystemError
from core.interfaces import InterAgentMessage

logger = logging.getLogger("jarvis.core.events.redis_bus")


class RedisEventBus(EventBus):
    """Production implementation of the global event bus using Redis Streams."""

    def __init__(
        self, host: str = "localhost", port: int = 6379, password: Optional[str] = None
    ) -> None:
        """Initialize the RedisEventBus with connection parameters.

        Args:
            host: Redis server host address.
            port: Redis server port number.
            password: Redis server auth password.
        """
        self.host = host
        self.port = port
        self.password = password
        self.client: Optional[aioredis.Redis] = None
        self._subscribers: Dict[
            str, List[tuple[str, Callable[[InterAgentMessage], Awaitable[None]]]]
        ] = {}
        self._active: bool = False
        self._listen_task: Optional[asyncio.Task[None]] = None
        self._dispatch_tasks: Set[asyncio.Task[None]] = set()

    async def initialize(self) -> None:
        """Establish connection pool to the Redis instance.

        Raises:
            JarvisSystemError: If Redis client initialization fails.
        """
        try:
            self.client = aioredis.Redis(
                host=self.host,
                port=self.port,
                password=self.password,
                decode_responses=True,
            )
            # Ping to verify active connection
            await self.client.ping()
            logger.info("Connected to Redis event bus at %s:%d", self.host, self.port)
        except Exception as err:
            raise JarvisSystemError(
                code="SYSTEM_001",
                message=f"Redis connection failed during initialization: {str(err)}",
            ) from err

    async def start(self) -> None:
        """Start listening for events on Redis Streams."""
        if not self.client:
            raise JarvisSystemError(
                code="SYSTEM_001",
                message="Cannot start RedisEventBus: Client is not initialized.",
            )
        self._active = True
        self._listen_task = asyncio.create_task(self._listen_loop())
        logger.info("RedisEventBus listener loop started.")

    async def stop(self) -> None:
        """Stop listening and close Redis connections."""
        self._active = False
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None

        pending_tasks = [task for task in self._dispatch_tasks if not task.done()]
        for task in pending_tasks:
            task.cancel()
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)
        self._dispatch_tasks.clear()

        if self.client:
            await self.client.close()
            self.client = None
        logger.info("RedisEventBus stopped and disconnected.")

    async def shutdown(self) -> None:
        """Deallocate registries and clear listeners."""
        self._subscribers.clear()
        self._active = False
        pending_tasks = [task for task in self._dispatch_tasks if not task.done()]
        for task in pending_tasks:
            task.cancel()
        if pending_tasks:
            await asyncio.gather(*pending_tasks, return_exceptions=True)
        self._dispatch_tasks.clear()
        logger.info("RedisEventBus shutdown complete.")

    async def publish(self, topic: str, message: InterAgentMessage) -> bool:
        """Publish a message payload to a Redis Stream topic.

        Args:
            topic: Redis stream key representing the topic (e.g. 'agent.task.started').
            message: The InterAgentMessage envelope.

        Returns:
            True if published successfully, False otherwise.

        Raises:
            JarvisSystemError: If publishing to Redis fails.
        """
        if not self._active or not self.client:
            logger.warning("Redis event bus is not active. Message dropped: %s", topic)
            return False

        logger.info("EventBus [Redis] Publish to '%s': %s", topic, message.action)
        try:
            # Add message to stream with cap maxlen 10000
            await self.client.xadd(
                name=topic,
                fields={"payload": message.model_dump_json()},
                maxlen=10000,
                approximate=True,
            )
            return True
        except Exception as err:
            raise JarvisSystemError(
                code="SYSTEM_999",
                message=f"Failed to publish event to Redis stream '{topic}': {str(err)}",
            ) from err

    async def subscribe(
        self,
        topic: str,
        callback: Callable[[InterAgentMessage], Awaitable[None]],
    ) -> str:
        """Register callback for a Redis Stream topic.

        Args:
            topic: Redis stream key.
            callback: Async callback function.

        Returns:
            A unique subscription ID.
        """
        sub_id = str(uuid4())
        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append((sub_id, callback))
        logger.debug("Subscribed to Redis stream '%s' with ID: %s", topic, sub_id)
        return sub_id

    async def unsubscribe(self, topic: str, sub_id: str) -> bool:
        """Unsubscribe callback from a Redis stream topic."""
        if topic in self._subscribers:
            listeners = self._subscribers[topic]
            for i, (listener_id, _) in enumerate(listeners):
                if listener_id == sub_id:
                    listeners.pop(i)
                    logger.debug("Unsubscribed ID %s from topic %s", sub_id, topic)
                    return True
        return False

    async def _listen_loop(self) -> None:
        """Listen loop reading new stream entries from Redis."""
        # Use a dict keeping track of last ID read for each stream topic
        last_ids: Dict[str, str] = {}

        while self._active and self.client:
            try:
                # Resolve active topics to poll
                topics = list(self._subscribers.keys())
                if not topics:
                    await asyncio.sleep(0.1)
                    continue

                # Initialize ID offset to '$' (new messages only) for newly added topics
                streams_dict: Dict[Any, Any] = {}
                for t in topics:
                    if t not in last_ids:
                        last_ids[t] = "$"
                    streams_dict[t] = last_ids[t]

                # Read from active streams with block timeout (100ms)
                results: Any = await self.client.xread(
                    streams_dict, count=10, block=100
                )
                if not results:
                    continue

                for stream_name, messages in results:
                    for msg_id, fields in messages:
                        last_ids[stream_name] = msg_id
                        raw_payload = fields.get("payload")
                        if not raw_payload:
                            continue

                        try:
                            # Deserialize message back to envelope model
                            msg = InterAgentMessage.model_validate_json(raw_payload)
                            # Dispatch to all callbacks for this topic
                            listeners = self._subscribers.get(stream_name, [])
                            for sub_id, callback in listeners:
                                task = asyncio.create_task(
                                    self._safe_dispatch(
                                        callback, msg, sub_id, stream_name
                                    )
                                )
                                self._dispatch_tasks.add(task)
                                task.add_done_callback(self._dispatch_tasks.discard)
                        except Exception as parse_err:
                            logger.error(
                                "Failed parsing message payload from stream %s: %s",
                                stream_name,
                                str(parse_err),
                            )

            except asyncio.CancelledError:
                break
            except Exception as loop_err:
                logger.error("Error in RedisEventBus listen loop: %s", str(loop_err))
                await asyncio.sleep(1.0)

    async def _safe_dispatch(
        self,
        callback: Callable[[InterAgentMessage], Awaitable[None]],
        message: InterAgentMessage,
        sub_id: str,
        topic: str,
    ) -> None:
        """Safely execute subscriber callback and log exceptions."""
        try:
            await callback(message)
        except Exception as err:
            logger.error(
                "Subscriber callback '%s' failed on Redis stream '%s': %s",
                sub_id,
                topic,
                str(err),
            )


stream_logger = logging.getLogger("jarvis")
stream_logger.setLevel(logging.INFO)
