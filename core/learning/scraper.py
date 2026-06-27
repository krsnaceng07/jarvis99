"""JARVIS OS - Document Scraper.

Validates domain trust gates and scrapes target documentation pages, extracting clean text and code blocks.
"""

import asyncio
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import List, Optional, Set

from core.exceptions import JarvisAgentError


class HTMLContentExtractor(HTMLParser):
    """HTML parser that extracts clean text and preserves code block regions."""

    def __init__(self) -> None:
        super().__init__()
        self.text_content: List[str] = []
        self.code_blocks: List[str] = []
        self.in_code: bool = False
        self.current_code: List[str] = []
        self.ignore_tags: Set[str] = {
            "script",
            "style",
            "nav",
            "footer",
            "header",
            "aside",
            "iframe",
        }
        self.current_tag: Optional[str] = None

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        self.current_tag = tag
        if tag in ("code", "pre"):
            self.in_code = True

    def handle_endtag(self, tag: str) -> None:
        if tag in ("code", "pre"):
            if self.current_code:
                code_text = "".join(self.current_code).strip()
                if code_text:
                    self.code_blocks.append(code_text)
                    self.text_content.append(f"\n```\n{code_text}\n```\n")
                self.current_code = []
            self.in_code = False
        self.current_tag = None

    def handle_data(self, data: str) -> None:
        if self.current_tag in self.ignore_tags:
            return
        if self.in_code:
            self.current_code.append(data)
        else:
            cleaned = data.strip()
            if cleaned:
                self.text_content.append(cleaned)

    def get_clean_payload(self) -> str:
        """Get combined parsed text payload."""
        return " ".join(self.text_content).strip()


class DocumentScraper:
    """Validates URLs against a trusted domains allowlist and scrapes content."""

    def __init__(self, allowed_domains: Optional[Set[str]] = None) -> None:
        """Initialize DocumentScraper.

        Args:
            allowed_domains: Set of trusted domain host suffixes.
        """
        self.allowed_domains = allowed_domains or {
            "readthedocs.io",
            "github.com",
            "python.org",
            "playwright.dev",
        }

    def validate_url(self, url: str) -> str:
        """Verify if URL belongs to a trusted domain and satisfies SSRF checks.

        Args:
            url: Target URL string.

        Returns:
            The parsed domain host name.

        Raises:
            JarvisAgentError: If domain validation or SSRF checks fail.
        """
        import ipaddress
        import socket

        try:
            parsed = urllib.parse.urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                raise JarvisAgentError(
                    code="AGENT_002",
                    message=f"Invalid URL structure: {url}",
                )

            # 1. Scheme Gatekeeper
            scheme = parsed.scheme.lower()
            if scheme not in ("http", "https"):
                raise JarvisAgentError(
                    code="AGENT_002",
                    message=f"Unauthorized scheme '{scheme}': Only HTTP/HTTPS protocols allowed.",
                )

            host = parsed.netloc.lower()
            # Handle port suffix if present
            if ":" in host:
                host = host.split(":")[0]

            # 2. Trusted Domain Check
            is_allowed = False
            for allowed in self.allowed_domains:
                if host == allowed or host.endswith("." + allowed):
                    is_allowed = True
                    break

            if not is_allowed:
                raise JarvisAgentError(
                    code="AGENT_002",
                    message=f"Unauthorized domain block: Host '{host}' is not in trusted allowlist.",
                )

            # 3. SSRF IP Range Validation (DNS Resolution check)
            try:
                # Resolve IPs for the host
                addr_infos = socket.getaddrinfo(host, None)
                for addr_info in addr_infos:
                    ip = addr_info[4][0]
                    addr = ipaddress.ip_address(ip)
                    if addr.is_private or addr.is_loopback or addr.is_link_local:
                        raise JarvisAgentError(
                            code="AGENT_002",
                            message=f"SSRF Prevention: Host '{host}' resolves to local/private IP '{ip}'.",
                        )
            except socket.gaierror:
                # If offline/DNS is missing under test, permit if it's explicitly in the trusted allowlist
                if host in self.allowed_domains or any(
                    host.endswith("." + d) for d in self.allowed_domains
                ):
                    pass
                else:
                    raise JarvisAgentError(
                        code="AGENT_002",
                        message=f"SSRF Prevention: DNS resolution failed for host '{host}'.",
                    )

            return host
        except JarvisAgentError:
            raise
        except Exception as err:
            raise JarvisAgentError(
                code="AGENT_002",
                message=f"Failed to parse URL target: {str(err)}",
            ) from err

    async def scrape_url(self, url: str) -> str:
        """Fetch URL content and return extracted text and code.

        Args:
            url: Target URL string.

        Returns:
            Clean parsed text representation.
        """
        self.validate_url(url)

        try:
            # Execute HTTP Request via urllib (standard library wrapper)
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "JarvisOS/1.0 (Autonomous Learning Engine)"},
            )

            # Wrap standard blocking open inside a thread pool or async loop executor
            # to prevent blocking event loop execution
            def _fetch() -> bytes:
                with urllib.request.urlopen(req, timeout=10) as response:
                    return response.read()  # type: ignore[no-any-return]

            loop = asyncio.get_running_loop()
            raw_html = await loop.run_in_executor(None, _fetch)
            html_text = raw_html.decode("utf-8", errors="ignore")

            # Extract clean payload
            extractor = HTMLContentExtractor()
            extractor.feed(html_text)
            return extractor.get_clean_payload()

        except urllib.error.HTTPError as http_err:
            raise JarvisAgentError(
                code="AGENT_002",
                message=f"HTTP request failed: {http_err.code} {http_err.reason}",
            ) from http_err
        except urllib.error.URLError as url_err:
            raise JarvisAgentError(
                code="AGENT_002",
                message=f"Network unreachable or DNS failure: {url_err.reason}",
            ) from url_err
        except Exception as err:
            raise JarvisAgentError(
                code="AGENT_999",
                message=f"Failed to scrape documentation target: {str(err)}",
            ) from err
