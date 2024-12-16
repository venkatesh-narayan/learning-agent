import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import aiohttp
from app.scripts.companies import get_all_companies, get_company_by_symbol
from app.scripts.rate_limiter import MultiAPIRateLimiter
from app.scripts.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class PolygonScraper(BaseScraper):
    """
    Polygon.io scraper for financial data with multi-key support.
    Rate limits per key: 5 requests/minute on free tier
    """

    def __init__(
        self, api_keys: List[str], bucket_name: str = "scraped-financial-data"
    ):
        super().__init__(bucket_name)
        self.rate_limiter = MultiAPIRateLimiter(
            {
                "polygon": {
                    "keys": api_keys,
                    "calls_per_second": 1.0,  # Aggregate limit
                    "calls_per_minute": 5,  # Per key limit
                }
            }
        )

        self.base_url = "https://api.polygon.io"  # Remove /v2 since versions vary

        # Endpoints we'll use
        self.endpoints = {
            "details": "/v3/reference/tickers/{ticker}",  # Basic company info
            "news": "/v2/reference/news",  # Company news
            "related": "/v1/related-companies/{ticker}",  # Related companies
            "financials": "/vX/reference/financials",  # Financial statements
        }

        # Track processed items
        self.processed_items = set()

        # Track company assignments per API key
        self.key_company_assignments = defaultdict(set)

    def _assign_companies_to_keys(self, symbols: List[str]) -> Dict[str, List[str]]:
        """Distribute companies across API keys evenly."""
        assignments = defaultdict(list)
        api_keys = self.rate_limiter.limiters["polygon"].api_keys

        for idx, symbol in enumerate(symbols):
            key = api_keys[idx % len(api_keys)]
            assignments[key].append(symbol)

        return assignments

    def _batch_symbols(self, symbols: List[str], batch_size: int) -> List[List[str]]:
        """Split symbols into batches for parallel processing."""
        return [
            symbols[i : i + batch_size]  # noqa
            for i in range(0, len(symbols), batch_size)
        ]

    async def scrape(
        self,
        start_date: datetime,
        symbols: Optional[List[str]] = None,
        quarters_back: int = 4,  # Number of quarters of financial data
        max_concurrent: int = 5,
        **unused_kwargs,
    ) -> Dict[str, int]:
        """
        Scrape financial data from Polygon using multiple API keys in parallel.
        Returns count of successful scrapes by data type.
        """
        if not symbols:
            symbols = [company["symbol"] for company in get_all_companies()]
            logger.info(
                f"[POLYGON] No symbols provided, using all {len(symbols)} companies"
            )

        results = defaultdict(int)
        company_assignments = self._assign_companies_to_keys(symbols)
        logger.info(
            f"[POLYGON] Processing {len(symbols)} companies with "
            f"{len(self.rate_limiter.limiters['polygon'].api_keys)} API keys"
        )

        async with aiohttp.ClientSession() as session:
            tasks = []

            # Process each API key's assigned companies
            for api_key, assigned_symbols in company_assignments.items():
                for symbol_batch in self._batch_symbols(
                    assigned_symbols, max_concurrent
                ):
                    task = self._process_company_batch(
                        session=session,
                        symbols=symbol_batch,
                        api_key=api_key,
                        quarters_back=quarters_back,
                    )
                    tasks.append(task)

            # Wait for all batches to complete
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Aggregate results
            for result in batch_results:
                if isinstance(result, dict):
                    for category, count in result.items():
                        results[category] += count
                elif isinstance(result, Exception):
                    logger.error(f"[POLYGON] Batch processing error: {str(result)}")

        logger.info(
            f"[POLYGON] Scraping complete. Results by category: "
            f"{', '.join(f'{k}={v}' for k, v in results.items())}"
        )
        return dict(results)

    async def _process_company_batch(
        self,
        session: aiohttp.ClientSession,
        symbols: List[str],
        api_key: str,
        quarters_back: int,
    ) -> Dict[str, int]:
        """Process a batch of companies using a specific API key."""
        results = defaultdict(int)

        for symbol in symbols:
            try:
                company = get_company_by_symbol(symbol)

                # Get company details
                await self.rate_limiter.acquire("polygon")
                details_success = await self._get_company_details(
                    session=session,
                    symbol=symbol,
                    company=company,
                    api_key=api_key,
                )
                if details_success:
                    results["details"] += 1

                # Get financial statements for recent quarters
                for quarter in range(quarters_back):
                    await self.rate_limiter.acquire("polygon")
                    financials_success = await self._get_financials(
                        session=session,
                        symbol=symbol,
                        company=company,
                        quarter_back=quarter,
                        api_key=api_key,
                    )
                    if financials_success:
                        results["financials"] += 1

                # Small delay between companies
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"[POLYGON] Error processing {symbol}: {str(e)}")
                continue

        return dict(results)

    async def _get_company_details(
        self,
        session: aiohttp.ClientSession,
        symbol: str,
        company: Dict,
        api_key: str,
    ) -> bool:
        """Get company details and key metrics."""
        try:
            url = f"{self.base_url}{self.endpoints['details'].format(ticker=symbol)}"

            async with session.get(url, params={"apiKey": api_key}) as response:
                if response.status != 200:
                    logger.error(
                        f"[POLYGON] Error fetching details for {symbol}: "
                        f"{response.status}"
                    )
                    return False

                data = await response.json()
                if not data.get("results"):
                    return False

                # Also get related news
                news_url = f"{self.base_url}{self.endpoints['news']}"
                async with session.get(
                    news_url,
                    params={
                        "apiKey": api_key,
                        "ticker": symbol,
                        "limit": 10,
                    },
                ) as news_response:
                    news_data = (
                        await news_response.json()
                        if news_response.status == 200
                        else None
                    )

                # Store details with news if available
                content = {
                    "company_details": data["results"],
                    "recent_news": (
                        news_data["results"]
                        if news_data and news_data.get("results")
                        else None
                    ),
                }

                await self.store_raw_content(
                    content_type="company_details",
                    identifier=f"polygon_details_{symbol}",
                    raw_content=content,
                    metadata={
                        "symbol": symbol,
                        "company_name": company.get("name", "Unknown"),
                        "sector": company.get("sector", "Unknown"),
                        "api_key_used": api_key,
                    },
                )

                return True

        except Exception as e:
            logger.error(f"[POLYGON] Error getting details for {symbol}: {str(e)}")
            return False

    async def _get_financials(
        self,
        session: aiohttp.ClientSession,
        symbol: str,
        company: Dict,
        quarter_back: int = 0,
        api_key: str = None,
    ) -> bool:
        """Get quarterly financial statements."""
        try:
            data = await self._fetch_financials(session, symbol, api_key)
            if not data:
                return False

            # Calculate the quarter we're fetching
            target_date = datetime.now() - timedelta(days=90 * quarter_back)
            identifier = (
                f"polygon_financials_{symbol}_"
                f"{target_date.year}Q{(target_date.month-1)//3 + 1}"
            )

            # Store financials
            await self.store_raw_content(
                content_type="financial_statements",
                identifier=identifier,
                raw_content=data,
                metadata={
                    "symbol": symbol,
                    "company_name": company.get("name", "Unknown"),
                    "sector": company.get("sector", "Unknown"),
                    "period": data.get("period_of_report_date"),
                    "quarter": (target_date.month - 1) // 3 + 1,
                    "year": target_date.year,
                    "api_key_used": api_key,
                },
            )

            return True

        except Exception as e:
            logger.error(f"[POLYGON] Error getting financials for {symbol}: {str(e)}")
            return False

    async def _fetch_financials(
        self, session: aiohttp.ClientSession, symbol: str, api_key: str
    ) -> Optional[Dict]:
        """Fetch financial statements for a company."""
        try:
            url = f"{self.base_url}{self.endpoints['financials']}"
            params = {
                "ticker": symbol,
                "apiKey": api_key,
                "limit": 100,  # Fetch more records
            }

            async with session.get(url, params=params) as response:
                if response.status == 404:
                    logger.error(f"[POLYGON] No financial data found for {symbol}")
                    return None
                elif response.status == 401:
                    logger.error(
                        f"[POLYGON] Authentication failed for {symbol} - verify API "
                        "key"
                    )
                    return None
                elif response.status == 429:
                    logger.warning(
                        f"[POLYGON] Rate limit hit for {symbol}, waiting..."
                    )
                    await asyncio.sleep(60)  # Wait for rate limit reset
                    return await self._fetch_financials(
                        session, symbol, api_key
                    )  # Retry
                elif response.status != 200:
                    logger.error(
                        f"[POLYGON] Error fetching financials for {symbol}: "
                        f"{response.status}"
                    )
                    return None

                data = await response.json()
                if not data.get("results"):
                    logger.warning(
                        f"[POLYGON] No financial results found for {symbol}"
                    )
                    return None
                return data
        except Exception as e:
            logger.error(f"[POLYGON] Error processing {symbol}: {str(e)}")
            return None

    async def close(self):
        """Cleanup any resources."""
        pass
