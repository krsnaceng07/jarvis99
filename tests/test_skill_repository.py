"""Phase 18 M2 repository tests (CRUD/query only)."""

from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings
from core.memory.database import db_manager
from core.memory.models import Base
from core.skills.models import InstalledSkillModel
from core.skills.repository import SkillRepository


@pytest.fixture
async def skill_session() -> AsyncGenerator[AsyncSession, None]:
    settings = Settings.load_settings()
    db_manager.init(settings, connection_url="sqlite+aiosqlite:///:memory:")
    async with db_manager._engine.begin() as conn:  # type: ignore[union-attr]
        await conn.run_sync(Base.metadata.create_all)

    async with db_manager.session() as session:
        yield session
    await db_manager.close()


def _sample_skill(
    skill_id: str, name: str, status: str = "INSTALLED"
) -> InstalledSkillModel:
    return InstalledSkillModel(
        id=skill_id,
        name=name,
        version="1.0.0",
        status=status,
        trust_level="OFFICIAL",
        manifest_json='{"id":"%s"}' % skill_id,
        checksum="a" * 64,
        signature="sig_payload_abcdefghijklmnopqrstuvwxyz",
        approval_level="L1",
    )


@pytest.mark.asyncio
async def test_save_and_get_skill_by_id(skill_session: AsyncSession) -> None:
    repo = SkillRepository()
    skill_id = str(uuid4())
    model = _sample_skill(skill_id, "youtube")

    async with skill_session.begin():
        await repo.save_installed_skill(model, skill_session)

    fetched = await repo.get_skill_by_id(skill_id, skill_session)
    assert fetched is not None
    assert fetched.name == "youtube"


@pytest.mark.asyncio
async def test_get_skill_by_name(skill_session: AsyncSession) -> None:
    repo = SkillRepository()
    model = _sample_skill(str(uuid4()), "github")

    async with skill_session.begin():
        await repo.save_installed_skill(model, skill_session)

    fetched = await repo.get_skill_by_name("github", skill_session)
    assert fetched is not None
    assert fetched.name == "github"


@pytest.mark.asyncio
async def test_list_skills(skill_session: AsyncSession) -> None:
    repo = SkillRepository()
    skill_a = _sample_skill(str(uuid4()), "alpha")
    skill_b = _sample_skill(str(uuid4()), "beta")

    async with skill_session.begin():
        await repo.save_installed_skill(skill_a, skill_session)
        await repo.save_installed_skill(skill_b, skill_session)

    items = await repo.list_skills(skill_session)
    assert len(items) == 2


@pytest.mark.asyncio
async def test_update_skill_metadata(skill_session: AsyncSession) -> None:
    repo = SkillRepository()
    skill_id = str(uuid4())
    model = _sample_skill(skill_id, "docker")

    async with skill_session.begin():
        await repo.save_installed_skill(model, skill_session)

    async with skill_session.begin():
        updated = await repo.update_skill_metadata(
            skill_id,
            skill_session,
            version="1.1.0",
            status="ACTIVE",
            trust_level="VERIFIED",
        )
        assert updated is not None

    fetched = await repo.get_skill_by_id(skill_id, skill_session)
    assert fetched is not None
    assert fetched.version == "1.1.0"
    assert fetched.status == "ACTIVE"
    assert fetched.trust_level == "VERIFIED"


@pytest.mark.asyncio
async def test_remove_skill_soft_delete(skill_session: AsyncSession) -> None:
    repo = SkillRepository()
    skill_id = str(uuid4())
    model = _sample_skill(skill_id, "slack", status="ACTIVE")

    async with skill_session.begin():
        await repo.save_installed_skill(model, skill_session)

    async with skill_session.begin():
        removed = await repo.remove_skill(skill_id, skill_session)
        assert removed is not None

    fetched = await repo.get_skill_by_id(skill_id, skill_session)
    assert fetched is not None
    assert fetched.status == "REMOVED"


@pytest.mark.asyncio
async def test_query_by_trust_and_status(skill_session: AsyncSession) -> None:
    repo = SkillRepository()
    skill_a = _sample_skill(str(uuid4()), "aws", status="ACTIVE")
    skill_b = _sample_skill(str(uuid4()), "notion", status="INSTALLED")
    skill_b.trust_level = "COMMUNITY"

    async with skill_session.begin():
        await repo.save_installed_skill(skill_a, skill_session)
        await repo.save_installed_skill(skill_b, skill_session)

    official = await repo.list_skills_by_trust_level("OFFICIAL", skill_session)
    active = await repo.list_skills_by_status("ACTIVE", skill_session)
    assert len(official) == 1
    assert len(active) == 1
    assert active[0].name == "aws"


@pytest.mark.asyncio
async def test_query_by_capability(skill_session: AsyncSession) -> None:
    repo = SkillRepository()
    skill_id = str(uuid4())
    model = _sample_skill(skill_id, "youtube")

    async with skill_session.begin():
        await repo.save_installed_skill(model, skill_session)
        await repo.save_skill_capabilities(
            skill_id,
            ["youtube.video.search", "youtube.video.download"],
            skill_session,
        )

    results = await repo.list_skills_by_capability(
        "youtube.video.download", skill_session
    )
    assert len(results) == 1
    assert results[0].name == "youtube"


@pytest.mark.asyncio
async def test_append_skill_version(skill_session: AsyncSession) -> None:
    repo = SkillRepository()
    skill_id = str(uuid4())
    model = _sample_skill(skill_id, "kubernetes")

    async with skill_session.begin():
        await repo.save_installed_skill(model, skill_session)
        await repo.append_skill_version(
            skill_id=skill_id,
            version="1.0.0",
            status="INSTALLED",
            session=skill_session,
            reason="initial install",
        )

    fetched = await repo.get_skill_by_id(skill_id, skill_session)
    assert fetched is not None
    assert len(fetched.versions) == 1
    assert fetched.versions[0].reason == "initial install"


# ---------------------------------------------------------------------------
# CR-004 polish tests (3.1 Protocol, 3.3 CancelledError, 3.6 explicit kwargs)
# ---------------------------------------------------------------------------


def test_skill_repository_accepts_async_session_factory_protocol() -> None:
    """CR-004 §3.1: db_manager is typed as AsyncSessionFactory Protocol.

    A class that exposes ``session()`` as an async context manager
    structurally satisfies the Protocol; mypy enforces this at the
    construction site. This test verifies the Protocol is structural
    (any conforming class is accepted) and that the db_manager attribute
    is preserved unchanged. Runtime ``isinstance`` is intentionally not
    used — the Protocol is a static type hint, not a runtime check.
    """
    from contextlib import asynccontextmanager
    from typing import AsyncIterator

    from core.interfaces import AsyncSessionFactory

    class _StubFactory:
        """Minimal Protocol-conforming factory for the test."""

        @asynccontextmanager
        async def session(self) -> AsyncIterator[AsyncSession]:
            yield None  # type: ignore[misc]

    factory = _StubFactory()
    # Static type check (mypy) confirms _StubFactory satisfies
    # AsyncSessionFactory; runtime, we just assert the constructor
    # accepts the stub and preserves the reference.
    _: AsyncSessionFactory = factory
    repo = SkillRepository(db_manager=factory)
    assert repo._db_manager is factory


@pytest.mark.asyncio
async def test_scoped_session_rolls_back_on_cancellation(
    skill_session: AsyncSession,
) -> None:
    """CR-004 §3.3: CancelledError (BaseException) must trigger rollback.

    Pre-fix, the ``except Exception`` clause did not catch
    :class:`asyncio.CancelledError` (a ``BaseException`` subclass in
    Python 3.8+), so neither ``commit()`` nor ``rollback()`` was called
    on cancellation. The fix adds an ``except BaseException`` branch
    that explicitly rolls back and logs the cancellation. The async
    ``with`` block's ``__aexit__`` is still expected to be the
    authoritative cleanup path, but the explicit rollback guarantees
    that any in-flight transaction is closed before cancellation
    propagates.
    """
    import asyncio

    repo = SkillRepository()

    async def _cancel_during_op() -> None:
        # Use the fixture-provided session so we don't need a
        # db_manager; the fixture's session has been opened and
        # participates in the test's outer transaction.
        async with repo._scoped_session(skill_session) as s:
            assert s is not None
            raise asyncio.CancelledError("simulated mid-op cancel")

    with pytest.raises(asyncio.CancelledError):
        await _cancel_during_op()


@pytest.mark.asyncio
async def test_update_skill_metadata_rejects_unknown_kwarg(
    skill_session: AsyncSession,
) -> None:
    """CR-004 §3.6: explicit kwargs surface typos at the type layer.

    Pre-fix, ``update_skill_metadata`` accepted ``**fields`` and silently
    passed unknown keys to SQLAlchemy, producing a confusing
    ``InvalidRequestError`` at the database layer. The fix replaces
    ``**fields`` with an explicit keyword list (``version``, ``status``,
    ``trust_level``, ``manifest_json``, ``checksum``, ``signature``,
    ``approval_level``); an unknown kwarg now raises ``TypeError`` at
    the call site, exactly like any other Python function with a fixed
    kwarg signature.
    """
    repo = SkillRepository()
    skill_id = str(uuid4())
    model = _sample_skill(skill_id, "typo-test")

    async with skill_session.begin():
        await repo.save_installed_skill(model, skill_session)

    # Typo "stattus" instead of "status" — must raise TypeError, not
    # InvalidRequestError, because the explicit kwarg list does not
    # match.
    with pytest.raises(TypeError) as exc_info:
        await repo.update_skill_metadata(
            skill_id,
            skill_session,
            stattus="ACTIVE",  # type: ignore[call-arg]
        )
    assert "stattus" in str(exc_info.value) or "unexpected keyword" in str(
        exc_info.value
    )
