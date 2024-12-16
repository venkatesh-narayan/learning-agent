import asyncio
import hashlib
import logging
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

import aiohttp
from app.scripts.companies import get_all_companies, get_company_by_symbol
from app.scripts.rate_limiter import MultiAPIRateLimiter
from app.scripts.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class NewsAPIScraper(BaseScraper):
    """
    NewsAPI scraper for financial news with multi-key support.
    Rate limits per key: 100 requests/day
    """

    def __init__(
        self, api_keys: List[str], bucket_name: str = "scraped-financial-data"
    ):
        super().__init__(bucket_name)
        self.rate_limiter = MultiAPIRateLimiter(
            {
                "newsapi": {
                    "keys": api_keys,
                    "calls_per_second": 1,  # Aggregate limit
                    "calls_per_day": 100,  # Per key limit
                }
            }
        )

        self.base_url = "https://newsapi.org/v2/everything"

        # Financial news search queries
        self.queries = [
            "earnings report",
            "financial results",
            "quarterly performance",
            "market analysis",
            "industry analysis",
            "stock market news",
            "economic indicators",
            "merger acquisition",
            "company guidance",
            "financial forecast",
        ]

        # Track processed articles to avoid duplicates
        self.processed_articles = set()

        # Track which queries each API key has processed
        self.key_query_assignments = defaultdict(set)

    def _generate_article_id(self, url: str) -> str:
        """Generate unique identifier for an article."""
        return f"news_{hashlib.sha256(url.encode()).hexdigest()}"

    def _assign_queries_to_keys(self) -> Dict[str, List[str]]:
        """Distribute search queries across API keys."""
        assignments = defaultdict(list)
        api_keys = self.rate_limiter.limiters["newsapi"].api_keys

        for idx, query in enumerate(self.queries):
            key = api_keys[idx % len(api_keys)]
            assignments[key].append(query)
        return assignments

    def _assign_companies_to_keys(self, symbols: List[str]) -> Dict[str, List[str]]:
        """Distribute companies across API keys for company-specific news."""
        assignments = defaultdict(list)
        api_keys = self.rate_limiter.limiters["newsapi"].api_keys

        for idx, symbol in enumerate(symbols):
            key = api_keys[idx % len(api_keys)]
            assignments[key].append(symbol)
        return assignments

    async def scrape(
        self,
        start_date: datetime,
        end_date: Optional[datetime] = None,
        symbols: Optional[List[str]] = None,
        max_articles_per_query: int = 100,
        max_concurrent: int = 5,
        **unused_kwargs,
    ) -> Dict[str, int]:
        """Scrape financial news articles using multiple API keys in parallel."""
        if not end_date:
            end_date = datetime.now()

        results = defaultdict(int)

        async with aiohttp.ClientSession() as session:
            # First scrape company-specific news
            if not symbols:
                symbols = [company["symbol"] for company in get_all_companies()]

            company_assignments = self._assign_companies_to_keys(symbols)
            company_tasks = []

            for api_key, assigned_symbols in company_assignments.items():
                for symbol_batch in self._batch_symbols(
                    assigned_symbols, max_concurrent
                ):
                    task = self._process_company_batch(
                        session=session,
                        symbols=symbol_batch,
                        api_key=api_key,
                        start_date=start_date,
                        end_date=end_date,
                        max_articles=max_articles_per_query,
                    )
                    company_tasks.append(task)

            # Then scrape general financial news
            query_assignments = self._assign_queries_to_keys()
            query_tasks = []

            for api_key, assigned_queries in query_assignments.items():
                for query_batch in self._batch_queries(
                    assigned_queries, max_concurrent
                ):
                    task = self._process_query_batch(
                        session=session,
                        queries=query_batch,
                        api_key=api_key,
                        start_date=start_date,
                        end_date=end_date,
                        max_articles=max_articles_per_query,
                    )
                    query_tasks.append(task)

            # Wait for all tasks to complete
            all_results = await asyncio.gather(
                *company_tasks, *query_tasks, return_exceptions=True
            )

            # Aggregate results
            for result in all_results:
                if isinstance(result, dict):
                    for category, count in result.items():
                        results[category] += count
                elif isinstance(result, Exception):
                    logger.error(f"[NEWS] Batch processing error: {str(result)}")

        return dict(results)

    def _batch_symbols(self, symbols: List[str], batch_size: int) -> List[List[str]]:
        """Split symbols into batches for parallel processing."""
        return [
            symbols[i : i + batch_size]  # noqa
            for i in range(0, len(symbols), batch_size)
        ]

    def _batch_queries(self, queries: List[str], batch_size: int) -> List[List[str]]:
        """Split queries into batches for parallel processing."""
        return [
            queries[i : i + batch_size]  # noqa
            for i in range(0, len(queries), batch_size)
        ]

    async def _process_company_batch(
        self,
        session: aiohttp.ClientSession,
        symbols: List[str],
        api_key: str,
        start_date: datetime,
        end_date: datetime,
        max_articles: int,
    ) -> Dict[str, int]:
        """Process a batch of companies using a specific API key."""
        results = defaultdict(int)

        for symbol in symbols:
            try:
                company = get_company_by_symbol(symbol)
                search_query = f'"{company["name"]}" OR "{symbol}"'

                await self.rate_limiter.acquire("newsapi")
                async with session.get(
                    self.base_url,
                    params={
                        "q": search_query,
                        "from": start_date.strftime("%Y-%m-%d"),
                        "to": end_date.strftime("%Y-%m-%d"),
                        "language": "en",
                        "sortBy": "relevancy",
                        "pageSize": max_articles,
                        "apiKey": api_key,
                    },
                ) as response:
                    if response.status != 200:
                        logger.error(
                            f"[NEWS] Error fetching news for {symbol}: "
                            f"{response.status}"
                        )
                        continue

                    data = await response.json()
                    articles = data.get("articles", [])

                    for article in articles:
                        article_id = self._generate_article_id(article["url"])

                        if article_id in self.processed_articles:
                            continue

                        # Skip if no meaningful content
                        if not article.get("content") and not article.get(
                            "description"
                        ):
                            continue

                        success = await self._store_article(
                            article, article_id, company=company, api_key=api_key
                        )
                        if success:
                            results["company_specific"] += 1
                            self.processed_articles.add(article_id)

            except Exception as e:
                logger.error(f"[NEWS] Error processing {symbol}: {str(e)}")

        return results

    async def _process_query_batch(
        self,
        session: aiohttp.ClientSession,
        queries: List[str],
        api_key: str,
        start_date: datetime,
        end_date: datetime,
        max_articles: int,
    ) -> Dict[str, int]:
        """Process a batch of general financial news queries."""
        results = defaultdict(int)

        for query in queries:
            try:
                await self.rate_limiter.acquire("newsapi")
                async with session.get(
                    self.base_url,
                    params={
                        "q": query,
                        "from": start_date.strftime("%Y-%m-%d"),
                        "to": end_date.strftime("%Y-%m-%d"),
                        "language": "en",
                        "sortBy": "relevancy",
                        "pageSize": max_articles,
                        "apiKey": api_key,
                    },
                ) as response:
                    if response.status != 200:
                        logger.error(
                            f"[NEWS] Error fetching news for query '{query}': "
                            f"{response.status}"
                        )
                        continue

                    data = await response.json()
                    articles = data.get("articles", [])

                    for article in articles:
                        article_id = self._generate_article_id(article["url"])

                        if article_id in self.processed_articles:
                            continue

                        success = await self._store_article(
                            article, article_id, query=query, api_key=api_key
                        )
                        if success:
                            results["general_financial"] += 1
                            self.processed_articles.add(article_id)

            except Exception as e:
                logger.error(f"[NEWS] Error processing query '{query}': {str(e)}")

        return results

    async def _store_article(
        self,
        article: Dict,
        article_id: str,
        company: Optional[Dict] = None,
        query: Optional[str] = None,
        api_key: str = None,
    ) -> bool:
        """Store news article with enhanced metadata."""
        try:
            # Process article content
            content = {
                "title": article.get("title", ""),
                "description": article.get("description", ""),
                "content": article.get("content", ""),
                "url": article.get("url", ""),
                "source": article.get("source", {}).get("name"),
                "published_at": article.get("publishedAt"),
                "author": article.get("author"),
            }

            # Prepare metadata
            metadata = {
                "type": "company_news" if company else "general_financial",
                "source": "newsapi",
                "published_at": article.get("publishedAt"),
                "api_key_used": api_key,
                "scraped_at": datetime.now().isoformat(),
            }

            # Add company info if available
            if company:
                metadata.update(
                    {
                        "symbol": company["symbol"],
                        "company_name": company["name"],
                        "sector": company["sector"],
                    }
                )

            # Add query info for general financial news
            if query:
                metadata["search_query"] = query

            # Store in GCS
            await self.store_raw_content(
                content_type="news_article",
                identifier=article_id,
                raw_content=content,
                metadata=metadata,
            )

            return True

        except Exception as e:
            logger.error(
                f"[NEWS] Error storing article {article.get('url')}: " f"{str(e)}"
            )
            return False

    async def close(self):
        """Cleanup any resources."""
        pass
