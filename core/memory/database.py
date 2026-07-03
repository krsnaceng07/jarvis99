"""JARVIS OS - Database Session Management.

Handles async SQLAlchemy engines, session creation, and connection pooling.
"""

import contextlib
from typing import Any, AsyncIterator, Dict, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.config import Settings
from core.exceptions import JarvisError, JarvisMemoryError


class DatabaseSessionManager:
    """Manages database async engine lifecycle and session factory creation."""

    def __init__(self) -> None:
        self._engine: Optional[AsyncEngine] = None
        self._sessionmaker: Optional[async_sessionmaker[AsyncSession]] = None

    def init(self, settings: Settings, connection_url: Optional[str] = None) -> None:
        """Initialize the async engine and sessionmaker from settings or direct URL.

        Args:
            settings: Loaded configuration settings.
            connection_url: Optional direct override URL.
        """
        if connection_url is None:
            db_cfg = settings.database
            # Check environment to resolve default SQLite dev fallback or postgres URL
            if db_cfg.host == "sqlite" or db_cfg.host == ":memory:":
                connection_url = f"sqlite+aiosqlite:///{db_cfg.name}"
            else:
                pw_str = f":{db_cfg.password}" if db_cfg.password else ""
                connection_url = (
                    f"postgresql+asyncpg://{db_cfg.username}{pw_str}@"
                    f"{db_cfg.host}:{db_cfg.port}/{db_cfg.name}"
                )

        is_sqlite = connection_url.startswith("sqlite")
        connect_args: Dict[str, Any] = {}

        if is_sqlite:
            # SQLite requires check_same_thread=False for async multithreaded context
            connect_args["check_same_thread"] = False
            self._engine = create_async_engine(
                connection_url,
                echo=settings.system.debug,
                connect_args=connect_args,
            )
        else:
            self._engine = create_async_engine(
                connection_url,
                echo=settings.system.debug,
                pool_size=20,
                max_overflow=10,
                pool_pre_ping=True,
            )

        self._sessionmaker = async_sessionmaker(
            bind=self._engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )

    async def close(self) -> None:
        """Dispose of connection resources and close the engine."""
        if self._engine is None:
            return
        await self._engine.dispose()
        self._engine = None
        self._sessionmaker = None

    @contextlib.asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Async context manager returning an AsyncSession with auto-rollback on error."""
        if self._sessionmaker is None:
            raise JarvisMemoryError(
                code="SYSTEM_001",
                message="Database session manager is not initialized.",
            )
        session = self._sessionmaker()
        try:
            yield session
        except JarvisError:
            await session.rollback()
            raise
        except Exception as e:
            await session.rollback()
            raise JarvisMemoryError(
                code="SYSTEM_999",
                message=f"Database transaction failed: {str(e)}",
            ) from e
        finally:
            await session.close()


db_manager = DatabaseSessionManager()
