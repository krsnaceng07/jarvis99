"""JARVIS OS - Tool SDK Base Classes and Manifest DTOs.

Defines the base interface for custom skills, execution result DTOs, and Pydantic manifest validators.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from core.tools.dto import RetryPolicy, ToolExecutionResult

__all__ = ["SkillManifest", "JarvisSkill", "ToolExecutionResult"]


class SkillManifest(BaseModel):
    """Pydantic schema validator for skill package manifest.json configurations."""

    name: str = Field(
        ...,
        pattern=r"^[a-z0-9_-]+$",
        description="Unique lowercase skill name identifier.",
    )
    version: str = Field(
        ..., pattern=r"^\d+\.\d+\.\d+$", description="SemVer version string."
    )
    entry_point: str = Field(
        default="main.py", description="Relative entry point file path."
    )
    permissions: List[str] = Field(
        default_factory=list, description="List of declared capabilities."
    )
    signature: str = Field(
        ..., description="SHA-256 digital signature of the skill package."
    )
    jarvis_api_version: str = Field(
        ...,
        pattern=r"^\d+\.\d+$",
        description="Compatible JARVIS API major.minor version.",
    )
    skill_version: str = Field(
        ..., pattern=r"^\d+\.\d+\.\d+$", description="Skill package SemVer version."
    )
    min_runtime_version: str = Field(
        ...,
        pattern=r"^\d+\.\d+$",
        description="Minimum JARVIS OS runtime version required.",
    )
    network_access: bool = Field(
        default=False, description="Whether network access is requested."
    )
    dependencies: List[str] = Field(
        default_factory=list, description="List of config dependency keys required."
    )
    timeout: float = Field(default=900.0, description="Execution limit in seconds.")
    approval_level: str = Field(
        default="L0", description="Target human approval clearance (L0-L3)."
    )
    supports_parallel: bool = Field(
        default=True, description="Indicates if task can run concurrently."
    )
    retry_policy: Optional[RetryPolicy] = Field(
        default=None, description="Custom fallback retry bounds."
    )
    sandbox_image: str = Field(
        default="python:3.12-slim", description="Whitelisted runtime Docker image."
    )
    resource_limit_mb: int = Field(
        default=512, description="RAM execution limit in MB."
    )
    jarvis_version: str = Field(
        default="1.0",
        pattern=r"^\d+\.\d+$",
        description="Minimum JARVIS OS platform version this skill is compatible with.",
    )
    capabilities: List[str] = Field(
        default_factory=list,
        description="Declarative capability tags (e.g. 'file_io', 'web_search', 'code_exec').",
    )

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, v: List[str]) -> List[str]:
        valid_permissions = {"network", "file_read", "file_write", "browser", "cli"}
        for p in v:
            if p not in valid_permissions:
                raise ValueError(
                    f"Invalid permission: {p}. Must be one of {list(valid_permissions)}"
                )
        return v


class JarvisSkill(ABC):
    """Abstract base class interface enforcing lifecycle methods for custom skills."""

    @abstractmethod
    async def initialize(self) -> bool:
        """Perform setup actions like database connections or loading config.

        Returns:
            True if initialization succeeded, False otherwise.
        """
        pass

    @abstractmethod
    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Core execution point for tool call.

        Args:
            arguments: Dictionary parameter payload.

        Returns:
            Dictionary containing result variables.
        """
        pass

    @abstractmethod
    async def shutdown(self) -> bool:
        """Resource cleanup block.

        Returns:
            True if cleanup succeeded, False otherwise.
        """
        pass
