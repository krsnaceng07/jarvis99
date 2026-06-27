"""JARVIS OS - Browser Action DTO Models.

Defines Pydantic-based structured instructions for browser automation commands.
"""

from typing import Union

from pydantic import BaseModel, Field


class BrowserAction(BaseModel):
    """Base class for all browser command DTOs."""

    pass


class Navigate(BrowserAction):
    """Navigate page viewport to target url."""

    url: str = Field(..., description="Target web page URL destination.")


class Click(BrowserAction):
    """Simulate cursor mouse click on matching element selector."""

    selector: str = Field(..., description="Query selector string targeting element.")


class Type(BrowserAction):
    """Focus element and inject keyboard typing text string."""

    selector: str = Field(..., description="Query selector targeting text inputs.")
    text: str = Field(..., description="Keyboard character input stream text.")


class Scroll(BrowserAction):
    """Scroll viewport coordinates."""

    direction: str = Field(
        "down", description="Direction target: 'down', 'up', 'left', 'right'."
    )
    amount: int = Field(200, description="Pixel scroll distance amount.")


class Hover(BrowserAction):
    """Hover cursor pointer over target element."""

    selector: str = Field(..., description="Target element query selector.")


class Upload(BrowserAction):
    """Upload target file reference path to matching input tag selector."""

    selector: str = Field(..., description="Input element query selector.")
    file_path: str = Field(..., description="Host file system path of file to upload.")


class Download(BrowserAction):
    """Simulate file download from target URL."""

    url: str = Field(..., description="Target file source URL.")


class Wait(BrowserAction):
    """Instruct browser to halt execution for duration or until selector presence matches."""

    seconds_or_selector: Union[float, str] = Field(
        ..., description="Duration float seconds, or target query selector string."
    )


class PressKey(BrowserAction):
    """Press a single keyboard key character."""

    key: str = Field(
        ..., description="Character name key (e.g. Enter, Escape, Backspace)."
    )
