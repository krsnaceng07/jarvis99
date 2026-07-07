"""
PHASE: 42
STATUS: IMPLEMENTATION
SPECIFICATION:
    docs/104_PHASE_42_IDENTITY_ENGINE_SPECIFICATION.md

IMPLEMENTATION PLAN:
    C:/Users/kcs23/.gemini/antigravity-ide/brain/21be4144-6686-48ed-8e46-74ce7e189cd4/implementation_plan.md

AUTHORITATIVE:
    NO
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from core.interfaces import EventBusInterface, InterAgentMessage
from core.memory.models import AgentIdentityModel, to_identity_dto
from core.reasoning.identity_repository import IdentityRepository

logger = logging.getLogger("jarvis.core.reasoning.identity")


class AgentIdentity(BaseModel):
    """Pydantic model representing an agent persona/identity configuration."""

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(..., description="Unique human-readable name of the persona/identity.")
    role: str = Field(..., description="Target role (e.g. 'developer', 'cybersecurity_expert').")
    system_prompt: str = Field(..., description="Standard system instructions for the LLM.")
    personality: Optional[str] = Field(default=None, description="Persona behavioral characteristics.")
    communication_style: Optional[str] = Field(default=None, description="Tone, formatting guidelines.")
    allowed_capabilities: List[str] = Field(default_factory=list, description="Capabilities allowed for this identity.")
    default_model: Optional[str] = Field(default=None, description="Model identifier to route to by default.")
    memory_scope: Optional[str] = Field(default=None, description="Scope boundary for memory retrieval.")
    permission_profile: Optional[str] = Field(default=None, description="Security permission profile name.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary custom settings.")
    is_active: bool = Field(default=False, description="Flag identifying the active system identity.")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Fallback identity details if database is empty
DEFAULT_IDENTITY = AgentIdentity(
    id=UUID("00000000-0000-0000-0000-000000000000"),
    name="JARVIS Default",
    role="assistant",
    system_prompt="You are JARVIS OS, a helpful, secure, and robust AI operating system assistant.",
    personality="Helpful, efficient, and precise.",
    communication_style="Clear, professional, and structured.",
    allowed_capabilities=["*"],
    default_model=None,
    memory_scope="global",
    permission_profile="admin",
    metadata={},
    is_active=True,
)


class IdentityService:
    """Coordinates active identity caching, database updates, memory flushes, and event publishing."""

    def __init__(
        self,
        repository: Optional[IdentityRepository] = None,
        event_bus: Optional[EventBusInterface] = None,
        working_memory: Optional[Any] = None,
        brain_context: Optional[Any] = None,
    ) -> None:
        """Initialize the IdentityService."""
        self.repository = repository or IdentityRepository()
        self.event_bus = event_bus
        self.working_memory = working_memory
        self.brain_context = brain_context
        self._cached_active_identity: Optional[AgentIdentity] = None

    async def get_active_identity(self, session: Optional[Any] = None) -> AgentIdentity:
        """Fetch the current active agent identity. Uses cache if available."""
        if self._cached_active_identity is not None:
            return self._cached_active_identity

        if session is not None:
            model = await self.repository.get_active_identity(session)
            if model:
                dto = to_identity_dto(model)
                self._cached_active_identity = dto
                return dto
        else:
            from core.memory.database import db_manager
            try:
                async with db_manager.session() as sess:
                    model = await self.repository.get_active_identity(sess)
                    if model:
                        dto = to_identity_dto(model)
                        self._cached_active_identity = dto
                        return dto
            except Exception as e:
                logger.warning("Database lookup for active identity failed, using default: %s", e)

        # Fallback if no active identity or DB access fails
        return DEFAULT_IDENTITY

    async def create_identity(self, identity: AgentIdentity, session: Optional[Any] = None) -> AgentIdentity:
        """Create and save a new agent identity record."""
        model = AgentIdentityModel(
            id=identity.id,
            name=identity.name,
            role=identity.role,
            system_prompt=identity.system_prompt,
            personality=identity.personality,
            communication_style=identity.communication_style,
            allowed_capabilities=identity.allowed_capabilities,
            default_model=identity.default_model,
            memory_scope=identity.memory_scope,
            permission_profile=identity.permission_profile,
            metadata_=identity.metadata,
            is_active=identity.is_active,
            created_at=identity.created_at,
            updated_at=identity.updated_at,
        )

        if session is not None:
            await self.repository.save_identity(model, session)
        else:
            from core.memory.database import db_manager
            async with db_manager.session() as sess:
                await self.repository.save_identity(model, sess)
                await sess.commit()

        # Emit identity.created event
        if self.event_bus:
            msg = InterAgentMessage(
                sender="identity_service",
                receiver="all",
                action="identity.created",
                body={
                    "identity_id": str(identity.id),
                    "name": identity.name,
                    "role": identity.role,
                },
            )
            await self.event_bus.publish("identity.created", msg)

        # If created as active, cache it immediately
        if identity.is_active:
            self._cached_active_identity = identity
            await self._apply_side_effects(identity)

        return identity

    async def activate_identity(self, identity_id: UUID, session: Optional[Any] = None) -> AgentIdentity:
        """Atomically set target identity as active and other records as inactive."""
        if session is not None:
            model = await self.repository.get_identity(identity_id, session)
            if not model:
                raise ValueError(f"Identity with ID {identity_id} not found.")
            await self.repository.activate_identity(identity_id, session)
            # Refresh model state
            await session.refresh(model)
            dto = to_identity_dto(model)
        else:
            from core.memory.database import db_manager
            async with db_manager.session() as sess:
                model = await self.repository.get_identity(identity_id, sess)
                if not model:
                    raise ValueError(f"Identity with ID {identity_id} not found.")
                await self.repository.activate_identity(identity_id, sess)
                await sess.commit()
                # Re-fetch or reconstruct from model values
                dto = to_identity_dto(model)
                dto.is_active = True

        self._cached_active_identity = dto
        await self._apply_side_effects(dto)

        # Emit identity.activated event
        if self.event_bus:
            msg = InterAgentMessage(
                sender="identity_service",
                receiver="all",
                action="identity.activated",
                body={
                    "identity_id": str(dto.id),
                    "name": dto.name,
                    "role": dto.role,
                },
            )
            await self.event_bus.publish("identity.activated", msg)

        return dto

    async def list_identities(self, session: Optional[Any] = None) -> List[AgentIdentity]:
        """List all configured identities."""
        if session is not None:
            models = await self.repository.list_identities(session)
            return [to_identity_dto(m) for m in models]
        else:
            from core.memory.database import db_manager
            async with db_manager.session() as sess:
                models = await self.repository.list_identities(sess)
                return [to_identity_dto(m) for m in models]

    async def delete_identity(self, identity_id: UUID, session: Optional[Any] = None) -> bool:
        """Delete an identity. If active, invalidates cache and sets DEFAULT."""
        deleted = False
        if session is not None:
            deleted = await self.repository.delete_identity(identity_id, session)
        else:
            from core.memory.database import db_manager
            async with db_manager.session() as sess:
                deleted = await self.repository.delete_identity(identity_id, sess)
                await sess.commit()

        if deleted:
            if self._cached_active_identity and self._cached_active_identity.id == identity_id:
                self._cached_active_identity = None
                await self._apply_side_effects(DEFAULT_IDENTITY)
            return True

        return False

    async def _apply_side_effects(self, identity: AgentIdentity) -> None:
        """Apply side effects of changing active identity (clearing working memory, updating context)."""
        if self.working_memory is not None:
            self.working_memory.clear()

        if self.brain_context is not None:
            self.brain_context.set("active_identity", identity.model_dump(mode="json"))

    def invalidate_cache(self) -> None:
        """Manually clear the active cached identity."""
        self._cached_active_identity = None
