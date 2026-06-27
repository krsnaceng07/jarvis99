"""JARVIS OS - PC Display Manager.

Coordinates multi-monitor boundaries, DPI scale values, and portrait/landscape screen rotations.
"""

from typing import Any, Dict, List


class DisplayManager:
    """Manages active screen coordinates mapping and scaling checks."""

    def __init__(self) -> None:
        """Initialize DisplayManager."""
        self.primary_monitor = {
            "index": 0,
            "width": 1920,
            "height": 1080,
            "dpi": 96,
            "scale": 1.0,
            "rotation": 0,  # Degrees: 0, 90, 180, 270
        }
        self.monitors: List[Dict[str, Any]] = [self.primary_monitor]
        self.virtual_screen = {"left": 0, "top": 0, "right": 1920, "bottom": 1080}

    def get_display_info(self) -> Dict[str, Any]:
        """Retrieve total layout dimensions.

        Returns:
            Display configuration values.
        """
        return {
            "primary": self.primary_monitor,
            "monitors": self.monitors,
            "virtual_screen": self.virtual_screen,
        }

    def is_within_bounds(self, x: int, y: int) -> bool:
        """Check coordinates are situated within active displays.

        Args:
            x: Horizontal coordinate.
            y: Vertical coordinate.

        Returns:
            True if target is safe and within bounds.
        """
        left = self.virtual_screen["left"]
        top = self.virtual_screen["top"]
        right = self.virtual_screen["right"]
        bottom = self.virtual_screen["bottom"]
        return left <= x <= right and top <= y <= bottom

    def map_to_primary(self, x: int, y: int) -> tuple[int, int]:
        """Translate relative coordinates mapping to the primary monitor scale.

        Args:
            x: Relative coordinate.
            y: Relative coordinate.

        Returns:
            Primary coordinates tuple.
        """
        scale = self.primary_monitor["scale"]
        return int(x * scale), int(y * scale)
