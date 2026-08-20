import asyncio
import math
import os
from datetime import datetime
from typing import Literal, Optional

from ddgs import DDGS
from pydantic import BaseModel, HttpUrl, Field
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from ..config import config
from .config import websearch_config, webfetch_config


class WebSearchNewsArticle(BaseModel):
    """Modelo para abstrair resultados de busca de notícias."""
    date: datetime = Field(..., description="Data e hora da publicação")
    title: str = Field(..., description="Título da notícia")
    body: str = Field(..., description="Conteúdo/resumo da notícia")
    url: HttpUrl = Field(..., description="URL da notícia")
    image: Optional[str] = Field(default="", description="URL da imagem de destaque")
    source: str = Field(..., description="Fonte/veículo da notícia")

    def __str__(self) -> str:
        """Representação em Markdown para prompts."""
        date_str = self.date.strftime("%d/%m/%Y %H:%M")
        return (
            f"## {self.title}\n\n"
            f"**{self.source}** · {date_str}\n\n"
            f"{self.body}\n\n"
            f"[Link para matéria]({self.url})"
        )

    def __repr__(self) -> str:
        """Representação técnica para debugging."""
        return (
            f"NewsArticle("
            f"date={self.date.isoformat()}, "
            f"title={self.title[:50]!r}{'...' if len(self.title) > 50 else ''}, "
            f"source={self.source!r}, "
            f"url={str(self.url)}"
            f")"
        )

async def web_search(
    query: str,
    max_results: int = 10,
    timelimit: Literal["d", "w", "m", "y"] | None = None,
) -> list[WebSearchNewsArticle]:
    """
    Search for news articles using DuckDuckGo.
    
    By default uses timelimit='m' (last month) — news searches without time filter
    can return empty for some generic queries even when recent news exists.

    Launches pages in parallel (limited by semaphore), but each page fails in
    isolation — an empty/failed page doesn't break others.
    
    Implements retry with exponential backoff for transient DDGS errors
    (rate limits, timeouts, etc).
    
    Returns a list of WebSearchNewsArticle (Pydantic model).
    """
    batches = _create_batches(max_results)
    sem = asyncio.Semaphore(websearch_config.MAX_CONCURRENCY)

    batch_results = await asyncio.gather(*[
        _run_batch(p, m, query, sem, timelimit) for p, m in batches
    ])

    all_results = _deduplicate_by_url(batch_results)
    articles = [WebSearchNewsArticle(**item) for item in all_results[:max_results]]
    return articles


def _create_batches(max_results: int, batch_size: int = websearch_config.BATCH_SIZE) -> list[tuple[int, int]]:
    """Return list of (page, batch_max_results) to cover total requested."""
    full_batches = max_results // batch_size
    remainder = max_results % batch_size
    batches = [(page, batch_size) for page in range(1, full_batches + 1)]
    if remainder:
        batches.append((full_batches + 1, remainder))
    return batches


async def _run_batch(page: int, page_max_results: int, query: str, sem: asyncio.Semaphore, timelimit: Literal["d", "w", "m", "y"] | None = None):
    """Execute search for a single page with semaphore and retry."""
    async with sem:
        await asyncio.sleep(websearch_config.DELAY * (page % websearch_config.MAX_CONCURRENCY))
        try:
            return await asyncio.to_thread(
                _sync_call_with_retry, page, page_max_results, query, timelimit
            )
        except Exception as e:
            print(f"Page {page} failed after {websearch_config.MAX_RETRIES} retries: {e!r}")
            return []


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
def _sync_call_with_retry(page: int, page_max_results: int, query: str, timelimit: Literal["d", "w", "m", "y"] | None = None):
    """Synchronous call with exponential retry for transient DDGS errors."""

    results = DDGS(proxy=config.PROXY_STRING, timeout=websearch_config.TIMEOUT).news(
        query=query,
        region=websearch_config.REGION,
        safesearch="off",
        timelimit=timelimit or websearch_config.TIMELIMIT,
        max_results=page_max_results,
        page=page,
        backend="auto",
    )
    return results if results else []

def _deduplicate_by_url(batch_results: list[list[dict]]) -> list[dict]:
    """Deduplicate results by URL, keeping first occurrence."""
    all_results, seen_urls = [], set()
    for page_result in batch_results:
        for item in page_result:
            url = item.get("url")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_results.append(item)
    return all_results
