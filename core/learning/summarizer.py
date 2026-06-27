"""JARVIS OS - Context Summarizer.

Filters visual fluff and extracts technical overviews, retaining code signatures, error descriptions, and snippet blocks.
"""

import re
from typing import List


class ContextSummarizer:
    """Summarizes scraped API docs while retaining technical specifications and code examples."""

    def __init__(self) -> None:
        """Initialize ContextSummarizer."""
        pass

    async def summarize(self, text: str) -> str:
        """Process document content and return a structured technical summary.

        Args:
            text: Raw extracted page text.

        Returns:
            Summarized string content.
        """
        if not text.strip():
            return ""

        # 1. Extract and preserve code block segments
        code_blocks: List[str] = re.findall(r"```.*?```", text, re.DOTALL)

        # 2. Extract function signatures, class definitions, and errors from raw text
        signatures: List[str] = []
        lines = text.split("\n")
        for line in lines:
            line_strip = line.strip()
            # Catch Python/JS signatures or error codes
            if (
                line_strip.startswith(("def ", "class ", "async def ", "function "))
                or "error" in line_strip.lower()
                or "exception" in line_strip.lower()
            ):
                if len(line_strip) < 150:
                    signatures.append(line_strip)

        # 3. Build a structured technical summary
        paragraphs = [p.strip() for p in text.split("  ") if p.strip()]
        overview = paragraphs[0] if paragraphs else ""
        # Truncate long overview paragraphs
        if len(overview) > 400:
            overview = overview[:400] + "..."

        summary_parts = []
        if overview:
            summary_parts.append(f"### Technical Overview\n{overview}")

        if signatures:
            sig_list = "\n".join(f"- `{sig}`" for sig in signatures[:10])
            summary_parts.append(f"### Code Signatures & API Context\n{sig_list}")

        if code_blocks:
            code_list = "\n\n".join(code_blocks[:3])
            summary_parts.append(f"### Code Snippets\n{code_list}")

        if not summary_parts:
            # Fallback to simple truncation
            return text[:1000]

        return "\n\n".join(summary_parts)
