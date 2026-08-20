import asyncio
import re
import httpx
import trafilatura
from typing import Literal, Optional

from loguru import logger
from pydantic import BaseModel, HttpUrl, Field
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from ..config import config
from .config import websearch_config, webfetch_config


class FetchedNewsArticleContent(BaseModel):
    """Model for extracted web content."""
    url: HttpUrl = Field(..., description="Original URL fetched")
    content: str = Field(..., description="Extracted content in markdown")
    is_from_wayback: bool = Field(default=False, description="Whether content was fetched from Wayback Machine")

    def __str__(self) -> str:
        """Markdown representation for prompts."""
        source_info = " (from Wayback Machine)" if self.is_from_wayback else ""
        return (
            f"## Content from {self.url}{source_info}\n\n"
            f"{self.content}"
        )

async def web_fetch(
    url: str,
    fallback_engine: Optional[Literal["wayback_machine"]] = None,
) -> FetchedNewsArticleContent:
    """
    Fetch and extract content from a URL using DDGS and trafilatura.

    Args:
        url: URL to fetch content from
        fallback_engine: Fallback strategy if URL is unavailable.
            - None: raise error if URL fails
            - "wayback_machine": try Wayback Machine CDX API if URL fails

    Returns:
        FetchedNewsArticleContent model with extracted markdown content.

    Raises:
        Exception: If fetch fails and no fallback_engine or fallback fails.
    """
    try:
        extracted = await asyncio.to_thread(_fetch_with_retry, url)
        html = extracted.get("content", "")

        if not html:
            raise ValueError(f"No HTML content extracted from {url}")

        content = await asyncio.to_thread(_extract_with_trafilatura, html)
        await asyncio.to_thread(_validate_extracted_content, content, url, html)

        return FetchedNewsArticleContent(
            url=url,
            content=content,
            is_from_wayback=False,
        )

    except Exception as e:
        if fallback_engine == "wayback_machine":
            logger.warning(f"Primary fetch failed: {e!r}. Trying Wayback Machine.")

            try:
                wayback_url = await asyncio.to_thread(_get_wayback_snapshot, url)
                logger.info(f"Found Wayback snapshot: {wayback_url}")

                extracted = await asyncio.to_thread(_fetch_with_retry, wayback_url)
                html = extracted.get("content", "")

                if not html:
                    raise ValueError(f"No HTML content extracted from Wayback snapshot: {wayback_url}")

                content = await asyncio.to_thread(_extract_with_trafilatura, html)
                await asyncio.to_thread(_validate_extracted_content, content, url, html)

                return FetchedNewsArticleContent(
                    url=url,
                    content=content,
                    is_from_wayback=True,
                )

            except Exception as wayback_error:
                raise RuntimeError(
                    f"Both primary fetch and Wayback Machine fallback failed. "
                    f"Primary: {e!r}. Wayback: {wayback_error!r}"
                ) from wayback_error

        else:
            raise


# Common error page indicators
ERROR_INDICATORS = [
    "página não encontrada",
    "page not found",
    "404",
    "not found",
    "erro 404",
    "conteúdo indisponível",
    "content unavailable",
    "página removida",
    "page removed",
]

# Generic error page patterns (regex)
ERROR_PATTERNS = [
    r"(?:Ops|Oops|Error)!?\s*$",
    r"página\s*(?:não\s*)?encontrada",
    r"404\s*(?:not\s*found)?",
]


def _validate_extracted_content(content: str, url: str, html: str) -> None:
    """Validate extracted content is real, not an error page.

    Uses scoring system combining multiple heuristics:
    - Hard rules: minimum length and word count (must pass)
    - Soft signals: error indicators, patterns, HTML ratio (contribute to validity score)

    Final score >= WEBFETCH_VALIDITY_THRESHOLD passes validation.

    Raises:
        ValueError: If content fails hard rules or validity score is too low.
    """
    content_len = len(content)
    word_count = len(content.split())
    html_len = len(html)

    # Hard rules: must pass
    if content_len < webfetch_config.MIN_CONTENT_LENGTH:
        raise ValueError(
            f"Content too short ({content_len} chars, min {webfetch_config.MIN_CONTENT_LENGTH}). "
            f"URL: {url}"
        )

    if word_count < webfetch_config.MIN_WORD_COUNT:
        raise ValueError(
            f"Content too brief ({word_count} words, min {webfetch_config.MIN_WORD_COUNT}). "
            f"URL: {url}"
        )

    # Soft scoring system (combined AND logic)
    validity_score = 0.0

    # Score based on content length (more is better)
    if content_len > 500:
        validity_score += 1.0
    if content_len > 1000:
        validity_score += 1.0
    if content_len > 2000:
        validity_score += 1.0

    # Penalty: Error indicators in early section
    early_content = content[:500].lower()
    for indicator in ERROR_INDICATORS:
        if indicator.lower() in early_content:
            validity_score -= 2.0
            break

    # Penalty: Generic error patterns in beginning
    for pattern in ERROR_PATTERNS:
        if re.search(pattern, content[:200], re.IGNORECASE | re.MULTILINE):
            validity_score -= 2.0
            break

    # Penalty: HTML-to-content ratio too high (error pages have bloated markup)
    ratio = html_len / content_len if content_len > 0 else float('inf')
    if ratio > 10:
        validity_score -= 1.5
    elif ratio > 5:
        validity_score -= 0.5
    else:
        validity_score += 0.5

    # Bonus: Decent word count (real content usually has 100+ words)
    if word_count > 100:
        validity_score += 1.0
    if word_count > 300:
        validity_score += 1.0
    if word_count > 500:
        validity_score += 1.0

    # Check final validity score
    if validity_score < webfetch_config.VALIDITY_THRESHOLD:
        raise ValueError(
            f"Content validity score too low ({validity_score:.1f}, min {webfetch_config.VALIDITY_THRESHOLD}). "
            f"Likely error page or low-quality content. URL: {url}"
        )


@retry(
    stop=stop_after_attempt(webfetch_config.WAYBACK_MAX_RETRIES),
    wait=wait_exponential(
        multiplier=webfetch_config.WAYBACK_RETRY_BASE_WAIT,
        min=webfetch_config.WAYBACK_RETRY_BASE_WAIT,
        max=webfetch_config.WAYBACK_RETRY_MAX_WAIT,
    ),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def _get_wayback_snapshot(url: str) -> str:
    """Get latest snapshot URL from Wayback Machine CDX API with retry."""
    params = {
        "url": url,
        "output": "json",
        "filter": "statuscode:200",
        "collapse": "urlkey",
        "limit": 1,
    }

    response = httpx.get(
        webfetch_config.WAYBACK_CDX_API,
        params=params,
        timeout=webfetch_config.WAYBACK_TIMEOUT,
    )
    response.raise_for_status()

    data = response.json()
    if len(data) < 2:
        raise ValueError(f"No snapshots found in Wayback Machine for {url}")

    # First row is headers, second row is the latest snapshot
    snapshot = data[1]
    timestamp = snapshot[1]

    return f"https://web.archive.org/web/{timestamp}/{url}"


def _extract_with_trafilatura(html: str) -> str:
    """Extract markdown from HTML using trafilatura."""
    return trafilatura.extract(
        html,
        include_tables=True,
        include_images=False,
        include_links=True,
        output_format="markdown",
    ) or ""


@retry(
    stop=stop_after_attempt(websearch_config.MAX_RETRIES),
    wait=wait_exponential(
        multiplier=websearch_config.RETRY_BASE_WAIT,
        min=websearch_config.RETRY_BASE_WAIT,
        max=websearch_config.RETRY_MAX_WAIT,
    ),
    retry=retry_if_exception_type(Exception),
    reraise=True,
)
def _fetch_with_retry(url: str) -> dict:
    """Fetch URL content using DDGS extract with retry."""
    from ddgs import DDGS
    return DDGS(proxy=config.PROXY_STRING, timeout=websearch_config.TIMEOUT).extract(
        url,
        fmt="text",
    )



