from dataclasses import dataclass
import hashlib
import json
import logging
from pathlib import Path
import sys
import time
from typing import Optional
from urllib.parse import urlparse
import io

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)

IGNORED_URL_SCHEMES = ("chrome:", "chrome-extension:", "javascript:", "about:", "file:", "data:", "blob:")


@dataclass
class BookmarkItem:
    """Represents a single parsed bookmark from Chrome."""
    id: str
    title: str
    url: str
    folder: str
    date_added: Optional[str] = None


@dataclass
class BookmarkFetchResult:
    """Represents the fetched and extracted content of a bookmarked web page."""
    bookmark: BookmarkItem
    text: str = ""
    content_type: str = ""
    status_code: Optional[int] = None
    is_success: bool = False
    error_message: Optional[str] = None
    content_hash: str = ""


class ChromeBookmarkParser:
    """Safely reads and parses Chrome bookmark JSON files (Bookmarks / AccountBookmarks)."""

    @staticmethod
    def is_valid_http_url(url: str) -> bool:
        """Check if URL uses HTTP/HTTPS and is not a browser-internal scheme."""
        if not url or not isinstance(url, str):
            return False
        clean_url = url.strip().lower()
        if any(clean_url.startswith(scheme) for scheme in IGNORED_URL_SCHEMES):
            return False
        parsed = urlparse(url)
        return parsed.scheme in ("http", "https") and bool(parsed.netloc)

    @classmethod
    def _extract_recursive(cls, node: dict, folder_path: str = "") -> list[BookmarkItem]:
        """Recursively walk through Chrome bookmark node tree."""
        results: list[BookmarkItem] = []
        node_type = node.get("type")
        name = node.get("name", "")

        if node_type == "url":
            url = node.get("url", "").strip()
            if not url:
                logger.debug(f"Skipping empty bookmark node: '{name}'")
            elif any(url.lower().startswith(scheme) for scheme in IGNORED_URL_SCHEMES):
                logger.info(f"Skipped internal/non-web bookmark scheme: '{name}' -> {url}")
            elif not cls.is_valid_http_url(url):
                logger.warning(f"Skipped invalid HTTP bookmark URL: '{name}' -> {url}")
            else:
                item_id = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
                results.append(
                    BookmarkItem(
                        id=item_id,
                        title=name.strip() or url,
                        url=url,
                        folder=folder_path or "Bookmarks",
                        date_added=node.get("date_added"),
                    )
                )
        elif node_type == "folder":
            current_folder = f"{folder_path}/{name}".strip("/") if folder_path else name.strip()
            for child in node.get("children", []):
                results.extend(cls._extract_recursive(child, current_folder))

        return results

    @classmethod
    def parse_file(cls, file_path: Path, max_retries: int = 3, retry_delay: float = 0.2) -> list[BookmarkItem]:
        """Parse a Chrome bookmark JSON file with retry logic for transient file locks.
        
        Note: Access is strictly read-only to guarantee Chrome data integrity.
        """
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"Chrome bookmarks file does not exist: {path}")
            return []

        data = None
        for attempt in range(1, max_retries + 1):
            try:
                # Read-only open with UTF-8 encoding
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    data = json.load(f)
                break
            except (PermissionError, OSError) as e:
                logger.warning(f"Attempt {attempt}/{max_retries} failed reading {path} due to file lock: {e}")
                if attempt < max_retries:
                    time.sleep(retry_delay * attempt)
                else:
                    logger.error(f"Failed to read {path} after {max_retries} attempts.")
                    return []
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in Chrome bookmarks file {path}: {e}")
                return []

        if not data or not isinstance(data, dict):
            return []

        roots = data.get("roots", {})
        bookmarks: list[BookmarkItem] = []
        for root_key, root_node in roots.items():
            if isinstance(root_node, dict):
                root_title = root_node.get("name") or root_key.replace("_", " ").title()
                for child in root_node.get("children", []):
                    bookmarks.extend(cls._extract_recursive(child, root_title))

        logger.info(f"Parsed {len(bookmarks)} valid HTTP bookmarks from {path.name}")
        return bookmarks

    @classmethod
    def discover_all_bookmarks(cls, custom_path: Optional[Path] = None) -> list[BookmarkItem]:
        """Discover and aggregate bookmarks across configured or all available Chrome profiles."""
        if custom_path and custom_path.exists():
            return cls.parse_file(custom_path)

        all_bookmarks: dict[str, BookmarkItem] = {}  # Deduplicate by URL

        # Auto-discover in LOCALAPPDATA across all profiles
        import os
        local_appdata = os.getenv("LOCALAPPDATA")
        if not local_appdata:
            if settings.CHROME_BOOKMARKS_PATH and settings.CHROME_BOOKMARKS_PATH.exists():
                return cls.parse_file(settings.CHROME_BOOKMARKS_PATH)
            return []

        chrome_user_data = Path(local_appdata) / "Google" / "Chrome" / "User Data"
        if not chrome_user_data.exists():
            if settings.CHROME_BOOKMARKS_PATH and settings.CHROME_BOOKMARKS_PATH.exists():
                return cls.parse_file(settings.CHROME_BOOKMARKS_PATH)
            return []

        # Scan Default and all Profile directories
        profile_dirs = ["Default", "Profile 1", "Profile 2", "Profile 3", "Profile 4", "Profile 5"]
        for profile in profile_dirs:
            prof_dir = chrome_user_data / profile
            if prof_dir.is_dir():
                for fname in ["Bookmarks", "AccountBookmarks"]:
                    b_file = prof_dir / fname
                    if b_file.exists():
                        for b in cls.parse_file(b_file):
                            if b.url in all_bookmarks:
                                existing = all_bookmarks[b.url]
                                logger.info(
                                    f"Skipped duplicate bookmark URL: '{b.title}' ({b.url}) "
                                    f"in [{profile}/{b.folder}], already tracked from [{existing.folder}]"
                                )
                            else:
                                all_bookmarks[b.url] = b

        # Fallback to configured path if no profiles found
        if not all_bookmarks and settings.CHROME_BOOKMARKS_PATH and settings.CHROME_BOOKMARKS_PATH.exists():
            for b in cls.parse_file(settings.CHROME_BOOKMARKS_PATH):
                if b.url not in all_bookmarks:
                    all_bookmarks[b.url] = b

        return list(all_bookmarks.values())




class BookmarkContentFetcher:
    """Fetches web page content over HTTP(S) and extracts readable article text."""

    def __init__(
        self,
        timeout: Optional[float] = None,
        user_agent: Optional[str] = None,
    ):
        self.timeout = timeout if timeout is not None else settings.BOOKMARK_FETCH_TIMEOUT
        self.user_agent = user_agent or USER_AGENT

    def _extract_pdf_bytes(self, content: bytes) -> str:
        """Extract text from raw PDF bytes."""
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(content))
            pages_text = []
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    pages_text.append(t.strip())
            return "\n\n".join(pages_text).strip()
        except Exception as e:
            logger.warning(f"Failed to extract PDF bytes: {e}")
            return ""

    def _extract_html_text(self, html_content: str, url: str) -> str:
        """Extract main article/page text using trafilatura with BeautifulSoup fallback."""
        text = ""
        # 1. Primary: Trafilatura main content extractor
        try:
            import trafilatura
            extracted = trafilatura.extract(
                html_content,
                url=url,
                include_links=False,
                include_comments=False,
                include_tables=True,
                output_format="txt",
                favor_precision=True,
            )
            if extracted and len(extracted.strip()) >= 50:
                text = extracted.strip()
        except Exception as e:
            logger.debug(f"Trafilatura extraction exception for {url}: {e}")

        if text:
            return text

        # 2. Fallback: BeautifulSoup text extraction
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_content, "html.parser")

            # Remove scripts, styles, nav, footer, headers
            for tag in soup(["script", "style", "nav", "footer", "noscript", "svg"]):
                tag.decompose()

            # Extract from main, article or body
            main_element = soup.find("article") or soup.find("main") or soup.find("body") or soup
            lines = (line.strip() for line in main_element.get_text().splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = "\n".join(chunk for chunk in chunks if chunk)
        except Exception as e:
            logger.debug(f"BeautifulSoup fallback extraction failed for {url}: {e}")

        return text.strip()

    def fetch(self, bookmark: BookmarkItem) -> BookmarkFetchResult:
        """Fetch and extract content from a bookmarked URL with detailed failure categorization."""
        url = bookmark.url
        headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf;q=0.8,*/*;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
        }

        try:
            with httpx.Client(
                timeout=self.timeout,
                follow_redirects=True,
                verify=True,
                headers=headers,
            ) as client:
                response = client.get(url)

                status = response.status_code
                content_type = response.headers.get("content-type", "").lower()

                # Handle HTTP Status Errors
                if status == 404:
                    return BookmarkFetchResult(
                        bookmark=bookmark,
                        status_code=404,
                        content_type=content_type,
                        error_message="HTTP 404: Page not found",
                    )
                elif status == 403:
                    return BookmarkFetchResult(
                        bookmark=bookmark,
                        status_code=403,
                        content_type=content_type,
                        error_message="HTTP 403: Access forbidden / Paywall",
                    )
                elif status == 401:
                    return BookmarkFetchResult(
                        bookmark=bookmark,
                        status_code=401,
                        content_type=content_type,
                        error_message="HTTP 401: Authentication required",
                    )
                elif status >= 400:
                    return BookmarkFetchResult(
                        bookmark=bookmark,
                        status_code=status,
                        content_type=content_type,
                        error_message=f"HTTP {status}: Remote server error",
                    )

                # Handle PDF Responses
                if "application/pdf" in content_type or url.lower().endswith(".pdf"):
                    extracted_text = self._extract_pdf_bytes(response.content)
                    if not extracted_text:
                        return BookmarkFetchResult(
                            bookmark=bookmark,
                            status_code=status,
                            content_type="application/pdf",
                            error_message="Failed to parse PDF document content",
                        )
                    content_hash = hashlib.sha256(extracted_text.encode("utf-8")).hexdigest()
                    return BookmarkFetchResult(
                        bookmark=bookmark,
                        text=extracted_text,
                        content_type="application/pdf",
                        status_code=status,
                        is_success=True,
                        content_hash=content_hash,
                    )

                # Handle Non-HTML Content (images, binaries, archives)
                if not any(t in content_type for t in ("text/html", "application/xhtml+xml", "text/plain", "text/markdown")):
                    return BookmarkFetchResult(
                        bookmark=bookmark,
                        status_code=status,
                        content_type=content_type,
                        error_message=f"Unsupported content type: {content_type.split(';')[0]}",
                    )

                # Extract HTML text
                extracted_text = self._extract_html_text(response.text, url)
                if not extracted_text or len(extracted_text) < 30:
                    return BookmarkFetchResult(
                        bookmark=bookmark,
                        status_code=status,
                        content_type=content_type,
                        error_message="No readable article text found on page (likely JavaScript-rendered or login shell)",
                    )

                content_hash = hashlib.sha256(extracted_text.encode("utf-8")).hexdigest()
                return BookmarkFetchResult(
                    bookmark=bookmark,
                    text=extracted_text,
                    content_type=content_type,
                    status_code=status,
                    is_success=True,
                    content_hash=content_hash,
                )

        except httpx.TimeoutException:
            return BookmarkFetchResult(
                bookmark=bookmark,
                error_message=f"Connection timed out after {self.timeout}s",
            )
        except httpx.ConnectError:
            return BookmarkFetchResult(
                bookmark=bookmark,
                error_message="Connection failed / DNS resolution error",
            )
        except httpx.HTTPError as e:
            return BookmarkFetchResult(
                bookmark=bookmark,
                error_message=f"HTTP transport error: {e}",
            )
        except Exception as e:
            return BookmarkFetchResult(
                bookmark=bookmark,
                error_message=f"Unexpected error fetching page: {e}",
            )
