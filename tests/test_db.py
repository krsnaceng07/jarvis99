"""JARVIS OS - Database Subsystem Tests.

Verifies async session manager lifecycle, transaction rollbacks, and schema models.
"""

from uuid import uuid4

import pytest
from sqlalchemy import select

from core.config import Settings
from core.exceptions import JarvisMemoryError
from core.memory.database import db_manager
from core.memory.models import AgentSession, Base


@pytest.mark.asyncio
async def test_database_manager_uninitialized() -> None:
    """Verify session raises JarvisMemoryError when uninitialized."""
    # Ensure manager is not initialized
    await db_manager.close()
    with pytest.raises(JarvisMemoryError) as exc_info:
        async with db_manager.session():
            pass
    assert exc_info.value.code == "SYSTEM_001"
    assert "not initialized" in exc_info.value.message


@pytest.mark.asyncio
async def test_database_transaction_rollback() -> None:
    """Verify changes are rolled back automatically when exception occurs."""
    settings = Settings.load_settings()
    # Initialize with local SQLite in-memory database
    db_manager.init(settings, connection_url="sqlite+aiosqlite:///:memory:")

    # Create tables
    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(Base.metadata.create_all)

    session_id = uuid4()

    # 1. Successful commit
    async with db_manager.session() as session:
        db_sess = AgentSession(id=session_id, status="active", config={})
        session.add(db_sess)
        await session.commit()

    # Verify session was persisted
    async with db_manager.session() as session:
        stmt = select(AgentSession).where(AgentSession.id == session_id)
        res = await session.execute(stmt)
        record = res.scalar_one_or_none()
        assert record is not None
        assert record.status == "active"

    # 2. Trigger rollback on exception
    with pytest.raises(JarvisMemoryError):
        async with db_manager.session() as session:
            # Modify record and raise exception
            stmt = select(AgentSession).where(AgentSession.id == session_id)
            res = await session.execute(stmt)
            record = res.scalar_one()
            record.status = "terminated"  # type: ignore[assignment]
            await session.flush()
            # Force failure
            raise RuntimeError("Simulated transaction error")

    # Verify status was NOT changed (rolled back)
    async with db_manager.session() as session:
        stmt = select(AgentSession).where(AgentSession.id == session_id)
        res = await session.execute(stmt)
        record = res.scalar_one()
        assert record.status == "active"

    await db_manager.close()
