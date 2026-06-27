"""JARVIS OS - Browser Permission Manager.

Gates downloads, geolocation queries, script injections, and whitelists outbound destinations.
"""

from typing import List, Optional

from core.exceptions import JarvisSystemError


class BrowserPermissionManager:
    """Restricts system actions and sanitizes runtime interactions."""

    def __init__(self, allowed_domains: Optional[List[str]] = None) -> None:
        """Initialize BrowserPermissionManager.

        Args:
            allowed_domains: Optional safe whitelist domain profiles.
        """
        self.allowed_domains = allowed_domains or [
            "google.com",
            "github.com",
            "python.org",
        ]
        self.granted_permissions = ["DOWNLOAD", "UPLOAD", "CLIPBOARD"]

    def verify_action_permission(self, permission_type: str) -> None:
        """Verify the selected permission parameter is granted.

        Args:
            permission_type: Target category (e.g. CAMERA).

        Raises:
            JarvisSystemError: If permission is rejected.
        """
        if permission_type not in self.granted_permissions:
            raise JarvisSystemError(
                code="PERMISSION_001",
                message=f"Browser action permission '{permission_type}' is denied.",
            )

    def verify_domain(self, url: str) -> None:
        """Check target URL destination against whitelists and block executable extensions.

        Args:
            url: Destination address.

        Raises:
            JarvisSystemError: If navigation violates whitelists or blocks.
        """
        # Block dangerous executable files
        lower_url = url.lower()
        for dangerous in (".exe", ".sh", ".bat", ".cmd", ".msi"):
            if lower_url.endswith(dangerous) or f"{dangerous}?" in lower_url:
                raise JarvisSystemError(
                    code="PERMISSION_002",
                    message="Download of executable files is blocked by browser policies.",
                )

        # Basic domain whitelisting check
        matched = False
        for domain in self.allowed_domains:
            if domain in lower_url:
                matched = True
                break

        # If it's a localhost, about:blank, or data url, allow it
        if (
            "localhost" in lower_url
            or "127.0.0.1" in lower_url
            or lower_url.startswith("about:")
            or lower_url.startswith("data:")
        ):
            matched = True

        if not matched:
            raise JarvisSystemError(
                code="PERMISSION_003",
                message=f"Navigation to domain in '{url}' is restricted by system policy.",
            )

    def verify_script_safety(self, script: str) -> None:
        """Sanitize script parameter payloads to prevent host system shell injections.

        Args:
            script: Javascript input payload.

        Raises:
            JarvisSystemError: If the script fails security validation checks.
        """
        forbidden_keywords = [
            "child_process",
            "subprocess",
            "spawn",
            "exec",
            "os.system",
            "eval",
        ]
        for word in forbidden_keywords:
            if word in script:
                raise JarvisSystemError(
                    code="PERMISSION_004",
                    message="JavaScript injection rejected: dangerous exploit pattern detected.",
                )
