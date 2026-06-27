"""JARVIS OS - Test Fixtures.

Defines shared fixtures for pytest executions, including temp directories and config overrides.
"""

import os
import tempfile
from typing import Generator

import pytest

from core.config import Settings


@pytest.fixture
def temp_key_path() -> Generator[str, None, None]:
    """Provide a temporary key file path that is cleaned up after testing."""
    with tempfile.NamedTemporaryFile(delete=False) as f:
        temp_path = f.name
    yield temp_path
    if os.path.exists(temp_path):
        os.remove(temp_path)


@pytest.fixture
def test_settings() -> Settings:
    """Provide a baseline Settings configuration for testing."""
    return Settings.load_settings()
