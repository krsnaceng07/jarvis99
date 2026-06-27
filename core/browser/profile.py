"""JARVIS OS - Browser Profiles and Context Manager.

Isolates browser cache folders and cookies across distinct user sessions.
"""

from typing import Any, Dict, Optional
from uuid import uuid4

from core.exceptions import JarvisSystemError


class BrowserProfileManager:
    """Manages profile setups and directory routing partitions."""

    def __init__(self, base_dir: str = "browser_profiles") -> None:
        """Initialize BrowserProfileManager.

        Args:
            base_dir: Root directory for profile files.
        """
        self.base_dir = base_dir
        self.profiles = ["Personal", "Work", "Testing", "Anonymous"]

    def get_profile_path(self, profile: str) -> str:
        """Resolve path coordinates for the selected profile directory.

        Args:
            profile: Target profile name identifier.

        Returns:
            Resolved path string.

        Raises:
            JarvisSystemError: If the profile name is invalid.
        """
        if profile not in self.profiles:
            raise JarvisSystemError(
                code="PROFILE_001",
                message=f"Browser profile '{profile}' is not registered.",
            )
        return f"{self.base_dir}/{profile.lower()}"


class BrowserContextManager:
    """Creates, isolates, and switches active session contexts storing cookie maps and histories."""

    def __init__(self, profile_manager: BrowserProfileManager) -> None:
        """Initialize BrowserContextManager.

        Args:
            profile_manager: Reference BrowserProfileManager.
        """
        self.profile_manager = profile_manager
        self.contexts: Dict[str, Dict[str, Any]] = {}
        self.active_context_id: Optional[str] = None

    def create_context(self, profile_name: str) -> str:
        """Instantiate an isolated session context inside the target profile.

        Args:
            profile_name: Target profile name (e.g. Work).

        Returns:
            UUID string representing the created context.
        """
        # Resolve target profile directory
        profile_path = self.profile_manager.get_profile_path(profile_name)

        context_id = str(uuid4())
        self.contexts[context_id] = {
            "id": context_id,
            "profile_name": profile_name,
            "profile_path": profile_path,
            "cookies": [],
            "local_storage": {},
            "session_storage": {},
            "permissions": ["DOWNLOAD", "UPLOAD", "CLIPBOARD"],
            "downloads": [],
        }

        if not self.active_context_id:
            self.active_context_id = context_id

        return context_id

    def close_context(self, context_id: str) -> None:
        """Discard an isolated context.

        Args:
            context_id: Target context identifier.

        Raises:
            JarvisSystemError: If context ID is missing.
        """
        if context_id not in self.contexts:
            raise JarvisSystemError(
                code="CONTEXT_001",
                message=f"Context ID '{context_id}' is not registered.",
            )
        del self.contexts[context_id]
        if self.active_context_id == context_id:
            self.active_context_id = (
                next(iter(self.contexts.keys())) if self.contexts else None
            )

    def switch_context(self, context_id: str) -> None:
        """Switch the active session context.

        Args:
            context_id: Target context identifier.

        Raises:
            JarvisSystemError: If context ID is missing.
        """
        if context_id not in self.contexts:
            raise JarvisSystemError(
                code="CONTEXT_001",
                message=f"Context ID '{context_id}' is not registered.",
            )
        self.active_context_id = context_id

    def get_context(self, context_id: str) -> Dict[str, Any]:
        """Retrieve state parameters for a context.

        Args:
            context_id: Target context identifier.

        Returns:
            Dictionary mapped context state.
        """
        if context_id not in self.contexts:
            raise JarvisSystemError(
                code="CONTEXT_001",
                message=f"Context ID '{context_id}' is not registered.",
            )
        return self.contexts[context_id]
