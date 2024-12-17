import asyncio
import hashlib
import logging
from typing import List, Optional

import aiohttp
from app.models.recommendations.content import ProcessedContent
from app.models.recommendations.strategy import SearchStrategy
from app.services.recommendations.cache.content_cache import ContentCache
from app.services.recommendations.content.extractors.financial import (
    FinancialContentExtractor,
)
from app.services.recommendations.perplexity.client import PerplexityClient
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class ContentDiscovery:
    """Find and process content based on search strategy."""

    def __init__(
        self,
        mongodb_uri: str,
        openai_engine: str,
        perplexity_api_key: str,
        cache: ContentCache,
        model: str = "llama-3.1-sonar-large-128k-online",
        max_concurrent_requests: int = 10,
        request_timeout: int = 5,
    ):
        self.api_key = perplexity_api_key
        self.model = model
        self.cache = cache
        self.max_concurrent = max_concurrent_requests
        self.timeout = request_timeout
        self.perplexity_client = PerplexityClient(
            perplexity_api_key, mongodb_uri, model
        )

        # Initialize extractor
        self.extractor = FinancialContentExtractor(mongodb_uri, openai_engine)

        # Semaphore for rate limiting
        self.request_semaphore = asyncio.Semaphore(max_concurrent_requests)

    async def execute_search(self, strategy: SearchStrategy) -> List[ProcessedContent]:
        """Execute search strategy to find valuable content."""
        try:
            discovered_urls = await self._get_search_urls(strategy.search_queries)
            if not discovered_urls:
                return []

            return await self._process_content(list(discovered_urls))

        except Exception as e:
            logger.error(f"Error executing search strategy: {str(e)}")
            return []

    async def _get_search_urls(self, queries: List[str]) -> set[str]:
        """Execute search queries and collect unique URLs."""
        try:
            search_tasks = [self._execute_single_search(query) for query in queries]

            search_results = await asyncio.gather(
                *search_tasks, return_exceptions=True
            )

            discovered_urls = set()
            for result in search_results:
                if isinstance(result, list):
                    discovered_urls.update(result)

            if not discovered_urls:
                logger.warning("No URLs found for any search query")

            logger.info(f"Discovered {len(discovered_urls)} URLs")
            return discovered_urls

        except Exception as e:
            logger.error(f"Error getting search URLs: {str(e)}")
            return set()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
    )
    async def _execute_single_search(self, query: str) -> List[str]:
        """Execute single search query with retries."""
        try:
            async with self.request_semaphore:
                _, urls, _ = await self.perplexity_client.get_response(query)

                # Skip videos (YouTube)
                urls = [url for url in urls if "youtube.com" not in url]

                logger.info(f"Found {len(urls)} sources for '{query}'")
                return urls

        except Exception as e:
            logger.error(f"Error executing search for '{query}': {str(e)}")
            return []

    async def _process_content(self, urls: List[str]) -> List[ProcessedContent]:
        """Process URLs into structured content using cache when available."""
        try:
            # Check cache first
            cached_content = await self.cache.get_content(urls)
            cached_urls = {c.url for c in cached_content}

            # Process new URLs
            new_urls = [url for url in urls if url not in cached_urls]
            if not new_urls:
                return cached_content

            # Process in batches
            new_content = []
            for i in range(0, len(new_urls), self.max_concurrent):
                batch = new_urls[i : i + self.max_concurrent]  # noqa
                batch_results = await self._process_batch(batch)
                new_content.extend(batch_results)

            # Cache new content
            if new_content:
                await self.cache.store_content(new_content)

            return [*cached_content, *new_content]

        except Exception as e:
            logger.error(f"Error processing content: {str(e)}")
            return cached_content if "cached_content" in locals() else []

    async def _process_batch(self, urls: List[str]) -> List[ProcessedContent]:
        """Process a batch of URLs concurrently."""
        try:
            tasks = [self._process_url(url) for url in urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            return [r for r in results if r is not None]

        except Exception as e:
            logger.error(f"Error processing batch: {str(e)}")
            return []

    async def _process_url(self, url: str) -> Optional[ProcessedContent]:
        """Process a single URL into structured content."""
        try:
            async with self.request_semaphore:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=self.timeout) as response:
                        if response.status != 200:
                            logger.warning(f"Failed to fetch {url}: {response.status}")
                            return None

                        html = await response.text()
                        return await self.extractor.extract(
                            content_id=self._generate_content_id(url),
                            url=url,
                            html=html,
                        )

        except asyncio.TimeoutError:
            logger.warning(f"Timeout fetching {url}")
            return None
        except Exception as e:
            logger.error(f"Error processing {url}: {str(e)}")
            return None

    def _generate_content_id(self, url: str) -> str:
        """Generate unique ID for content."""
        return hashlib.sha256(url.encode()).hexdigest()[:16]
