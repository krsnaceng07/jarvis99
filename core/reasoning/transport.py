"""JARVIS OS - HTTP Transport Layer.

Defines the HTTP transport contract and urllib-based async implementations.
"""

import asyncio
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import AsyncIterator, Dict, Optional, Union, cast

from core.exceptions import (
    AuthenticationError,
    RateLimitError,
    TransportError,
)
from core.exceptions import (
    TimeoutError as JarvisTimeoutError,
)


class IHttpTransport(ABC):
    """Abstract interface defining required requests and stream requests."""

    @abstractmethod
    async def request(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        data: Optional[bytes] = None,
        timeout: float = 30.0,
    ) -> bytes:
        """Send a standard HTTP request and return raw response bytes."""
        pass

    @abstractmethod
    async def stream_request(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        data: Optional[bytes] = None,
        timeout: float = 30.0,
    ) -> AsyncIterator[bytes]:
        """Send an HTTP request and stream the resulting response chunks."""
        pass


class UrllibTransport(IHttpTransport):
    """Concrete IHttpTransport implementation built on top of urllib standard library."""

    async def request(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        data: Optional[bytes] = None,
        timeout: float = 30.0,
    ) -> bytes:
        """Execute non-blocking HTTP request using urllib."""
        req = urllib.request.Request(url, headers=headers, method=method, data=data)
        loop = asyncio.get_running_loop()

        def _execute() -> bytes:
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return cast(bytes, resp.read())
            except urllib.error.HTTPError as err:
                self._map_http_error(err)
                raise
            except urllib.error.URLError as err:
                raise TransportError(
                    code="TRANS_001",
                    message=f"Network connection failed: {err.reason}",
                ) from err
            except TimeoutError as err:
                raise JarvisTimeoutError(
                    code="TRANS_002",
                    message="Request timed out.",
                ) from err
            except Exception as err:
                raise TransportError(
                    code="TRANS_999",
                    message=f"HTTP request failed: {err}",
                ) from err

        return await loop.run_in_executor(None, _execute)

    async def stream_request(
        self,
        method: str,
        url: str,
        headers: Dict[str, str],
        data: Optional[bytes] = None,
        timeout: float = 30.0,
    ) -> AsyncIterator[bytes]:
        """Execute streaming HTTP request using urllib and async iterator yields."""
        req = urllib.request.Request(url, headers=headers, method=method, data=data)
        queue: asyncio.Queue[Optional[Union[bytes, Exception]]] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        # Run connection and reading in a background thread to prevent blocking the event loop
        def _read_stream() -> None:
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    while True:
                        # Read small chunks to maintain dynamic stream resolution
                        chunk = resp.read(1024)
                        if not chunk:
                            break
                        # Submit bytes to the async queue
                        loop.call_soon_threadsafe(queue.put_nowait, chunk)
            except urllib.error.HTTPError as err:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    self._map_http_error_to_exception(err),
                )
                return
            except urllib.error.URLError as err:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    TransportError(
                        code="TRANS_001",
                        message=f"Network connection failed: {err.reason}",
                    ),
                )
                return
            except TimeoutError:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    JarvisTimeoutError(
                        code="TRANS_002",
                        message="Request timed out.",
                    ),
                )
                return
            except Exception as err:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    TransportError(
                        code="TRANS_999",
                        message=f"HTTP request failed: {err}",
                    ),
                )
                return
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        # Run thread in executor
        loop.run_in_executor(None, _read_stream)

        class StreamIterator:
            def __init__(
                self, q: asyncio.Queue[Optional[Union[bytes, Exception]]]
            ) -> None:
                self.q = q

            def __aiter__(self) -> "StreamIterator":
                return self

            async def __anext__(self) -> bytes:
                item = await self.q.get()
                if item is None:
                    raise StopAsyncIteration
                if isinstance(item, Exception):
                    raise item
                return item

        return cast(AsyncIterator[bytes], StreamIterator(queue))

    def _map_http_error(self, err: urllib.error.HTTPError) -> None:
        """Map urllib HTTPError to unified ModelProvider exception."""
        raise self._map_http_error_to_exception(err)

    def _map_http_error_to_exception(self, err: urllib.error.HTTPError) -> Exception:
        """Helper to instantiate mapped exception classes."""
        status = err.code
        body = ""
        try:
            body = err.read().decode("utf-8")
        except Exception:
            pass

        if status in (401, 403):
            return AuthenticationError(
                code="AUTH_001",
                message=f"API key authentication rejected ({status}): {body}",
            )
        if status == 429:
            return RateLimitError(
                code="RATE_001",
                message=f"API request rate limits hit ({status}): {body}",
            )
        if status == 408:
            return JarvisTimeoutError(
                code="TRANS_002",
                message="HTTP gateway timeout received.",
            )
        return TransportError(
            code="TRANS_HTTP",
            message=f"Server returned status code {status}: {body}",
        )
