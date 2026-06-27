"""JARVIS OS - Configuration and Settings.

Loads system configurations from YAML files and environment overrides using Pydantic.
"""

import os
from typing import Any, Dict, Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.exceptions import JarvisSystemError


class SystemConfig(BaseModel):
    """Configuration mapping for system environment profile and debugging settings."""

    environment: str = Field(default="production")
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")


class DatabaseConfig(BaseModel):
    """Configuration mapping for Postgres database connections."""

    host: str = Field(default="localhost")
    port: int = Field(default=5432)
    name: str = Field(default="jarvis_db")
    username: str = Field(default="jarvis_user")
    password: str = Field(default="")


class RedisConfig(BaseModel):
    """Configuration mapping for Redis event stream broker connections."""

    host: str = Field(default="localhost")
    port: int = Field(default=6379)


class VaultConfig(BaseModel):
    """Configuration mapping for secure vault paths."""

    encryption_key_path: str = Field(default="secrets/master.key")


class EmbeddingConfig(BaseModel):
    """Configuration mapping for embedding models and providers."""

    provider: str = Field(default="mock")
    model: str = Field(default="mock-model")
    dimensions: int = Field(default=384)  # Default dimension (e.g. BGE or Mock)
    timeout: float = Field(default=10.0)  # Timeout in seconds


class MemoryRetrievalConfig(BaseModel):
    """Configuration mapping for personal memory retrieval limits and budgets."""

    tier1_limit: int = Field(default=20)
    tier2_limit: int = Field(default=20)
    tier3_limit: int = Field(default=30)
    tier4_limit: int = Field(default=10)
    semantic_top_k: int = Field(default=15)


class MemoryConfig(BaseModel):
    """Configuration mapping for personal memory settings."""

    disable_auto_memory: bool = Field(default=False)
    retrieval: MemoryRetrievalConfig = Field(default_factory=MemoryRetrievalConfig)


class Settings(BaseSettings):
    """Unified Settings container validating configurations and environment overrides."""

    system: SystemConfig = Field(default_factory=SystemConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    vault: VaultConfig = Field(default_factory=VaultConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)

    model_config = SettingsConfigDict(
        env_prefix="JARVIS_",
        env_nested_delimiter="__",
    )

    @classmethod
    def load_settings(cls, yaml_path: Optional[str] = None) -> "Settings":
        """Load settings from a YAML configuration file combined with environment overrides.

        Args:
            yaml_path: Optional path to the configuration YAML file.

        Returns:
            Settings: A validated Settings configuration model instance.

        Raises:
            JarvisSystemError: If config file is missing or contains invalid fields.
        """
        config_dict: Dict[str, Any] = {}

        if yaml_path and os.path.exists(yaml_path):
            try:
                with open(yaml_path, "r", encoding="utf-8") as file:
                    loaded = yaml.safe_load(file)
                    if isinstance(loaded, dict):
                        config_dict = loaded
            except Exception as err:
                raise JarvisSystemError(
                    code="SYSTEM_001",
                    message=f"Failed parsing configuration YAML file '{yaml_path}': {str(err)}",
                ) from err
        elif yaml_path:
            raise JarvisSystemError(
                code="SYSTEM_001",
                message=f"Configuration file not found: {yaml_path}",
            )

        try:
            # Pydantic Settings automatically resolves env variables prefix 'JARVIS_'
            return cls(**config_dict)
        except Exception as validation_err:
            raise JarvisSystemError(
                code="SYSTEM_001",
                message=f"Configuration validation failed: {str(validation_err)}",
            ) from validation_err
