import asyncio
import hashlib
import logging
import re
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

import aiohttp
import feedparser
from app.scripts.companies import get_all_companies, get_company_by_symbol
from app.scripts.rate_limiter import MultiAPIRateLimiter
from app.scripts.scrapers.base import BaseScraper
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class RSSFeedScraper(BaseScraper):
    """RSS feed scraper for company press releases with parallel processing."""

    def __init__(
        self,
        api_keys: List[str],  # API keys for any authenticated feeds
        bucket_name: str = "scraped-financial-data",
        max_concurrent: int = 5,
    ):
        super().__init__(bucket_name)
        self.max_concurrent = max_concurrent

        # Initialize rate limiter for authenticated feeds
        self.rate_limiter = MultiAPIRateLimiter(
            {
                "rss_auth": {
                    "keys": api_keys,
                    "calls_per_second": 2,  # Aggregate limit
                    "calls_per_minute": 60,  # Per key limit
                }
            }
        )

        # Common IR RSS feed patterns
        self.feed_patterns = [
            "{base_url}/feed",
            "{base_url}/newsroom/feed",
            "{base_url}/press-releases/feed",
            "{base_url}/investors/feed",
            "{base_url}/news/feed",
            "{base_url}/media/feed",
            "{base_url}/corporate/feed",
            "{base_url}/ir/feed",
            "{base_url}/investor-relations/feed",
            "{base_url}/company-news/feed",
        ]

        # Track processed entries
        self.processed_entries = set()

        # Track company assignments per API key
        self.key_company_assignments = defaultdict(set)

    def _generate_entry_id(self, url: str) -> str:
        """Generate unique identifier for a feed entry."""
        return f"rss_{hashlib.sha256(url.encode()).hexdigest()}"

    def _assign_companies_to_keys(
        self, symbols: List[str], api_keys: List[str]
    ) -> Dict[str, List[str]]:
        """Distribute companies across API keys evenly."""
        assignments = defaultdict(list)
        for idx, symbol in enumerate(symbols):
            key = api_keys[idx % len(api_keys)] if api_keys else None
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
        prioritize_sectors: Optional[List[str]] = None,
        **unused_kwargs,
    ) -> Dict[str, int]:
        """Scrape company RSS feeds using multiple API keys in parallel."""
        if not symbols:
            companies = get_all_companies()
            if prioritize_sectors:
                companies.sort(
                    key=lambda x: (
                        prioritize_sectors.index(x["sector"])
                        if x["sector"] in prioritize_sectors
                        else len(prioritize_sectors)
                    )
                )
            symbols = [company["symbol"] for company in companies]

        results = defaultdict(int)
        api_keys = (
            self.rate_limiter.limiters["rss_auth"].api_keys
            if hasattr(self.rate_limiter, "limiters")
            else []
        )
        company_assignments = self._assign_companies_to_keys(symbols, api_keys)

        # Process companies in parallel batches
        async with aiohttp.ClientSession() as session:
            tasks = []

            for api_key, assigned_symbols in company_assignments.items():
                for symbol_batch in self._batch_symbols(
                    assigned_symbols, self.max_concurrent
                ):
                    task = self._process_company_batch(
                        session=session,
                        symbols=symbol_batch,
                        api_key=api_key,
                        start_date=start_date,
                    )
                    tasks.append(task)

            # Wait for all batches to complete
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Aggregate results
            for result in batch_results:
                if isinstance(result, dict):
                    for sector, count in result.items():
                        results[sector] += count
                elif isinstance(result, Exception):
                    logger.error(f"[RSS] Batch processing error: {str(result)}")

        return dict(results)

    async def _process_company_batch(
        self,
        session: aiohttp.ClientSession,
        symbols: List[str],
        api_key: Optional[str],
        start_date: datetime,
    ) -> Dict[str, int]:
        """Process a batch of companies using a specific API key."""
        results = defaultdict(int)

        for symbol in symbols:
            try:
                company = get_company_by_symbol(symbol)
                if not company:
                    logger.error(f"[RSS] Company not found for symbol {symbol}")
                    continue

                base_url = f"https://{company['domain']}"
                logger.info(f"[RSS] Processing {company['name']} ({base_url})")

                # Try different feed patterns with timeout
                for pattern in self.feed_patterns:
                    feed_url = pattern.format(base_url=base_url)

                    try:
                        headers = (
                            {"Authorization": f"Bearer {api_key}"} if api_key else {}
                        )

                        if api_key:
                            await self.rate_limiter.acquire("rss_auth")

                        # Add timeout to avoid hanging
                        async with session.get(
                            feed_url,
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=10, connect=5),
                        ) as response:
                            if response.status == 404:
                                continue
                            elif response.status != 200:
                                logger.warning(
                                    f"[RSS] Status {response.status} for {feed_url}"
                                )
                                continue

                            feed_content = await response.text()
                            feed = await self._parse_feed(feed_content)

                            if not feed or not feed.entries:
                                continue

                            # Process entries with timeout
                            entry_tasks = []
                            for entry in feed.entries:
                                published = self._parse_date(entry.get("published"))
                                if not published or published < start_date:
                                    continue

                                entry_tasks.append(
                                    asyncio.wait_for(
                                        self._store_entry(
                                            entry=entry,
                                            feed_url=feed_url,
                                            company=company,
                                            published=published,
                                            api_key=api_key,
                                        ),
                                        timeout=5,
                                    )
                                )

                            if entry_tasks:
                                # Process entries concurrently with error handling
                                entry_results = await asyncio.gather(
                                    *entry_tasks, return_exceptions=True
                                )
                                for result in entry_results:
                                    if isinstance(result, Exception):
                                        logger.warning(
                                            "[RSS] Entry processing error: "
                                            f"{str(result)}"
                                        )
                                    elif result:
                                        results[company.get("sector", "Unknown")] += 1

                    except asyncio.TimeoutError:
                        logger.warning(f"[RSS] Timeout fetching {feed_url}")
                        continue
                    except aiohttp.ClientError as e:
                        logger.warning(
                            f"[RSS] Connection error for {feed_url}: {str(e)}"
                        )
                        continue
                    except Exception as e:
                        logger.error(
                            f"[RSS] Unexpected error processing {feed_url}: {str(e)}"
                        )
                        continue

            except Exception as e:
                logger.error(f"[RSS] Error processing {symbol}: {str(e)}")
                continue

        return results

    async def _parse_feed(self, content: str) -> feedparser.FeedParserDict:
        """Parse RSS feed content asynchronously."""
        return await asyncio.get_event_loop().run_in_executor(
            None, feedparser.parse, content
        )

    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse date from feed entry."""
        if not date_str:
            return None

        try:
            from dateutil import parser
            from dateutil import tz

            # Define timezone mappings
            tzinfos = {"PST": tz.gettz("US/Pacific")}

            # Try feedparser's built-in parsing first
            parsed = feedparser.parse(f"<item><pubDate>{date_str}</pubDate></item>")
            if parsed.entries and parsed.entries[0].get("published_parsed"):
                time_tuple = parsed.entries[0].published_parsed
                return datetime(*time_tuple[:6], tzinfo=tz.UTC).astimezone(tz.UTC)

            # Try dateutil parser with timezone info
            return parser.parse(date_str, tzinfos=tzinfos).astimezone(tz.UTC)
        except Exception:
            return None

    async def _store_entry(
        self,
        entry: Dict,
        feed_url: str,
        company: Dict,
        published: datetime,
        api_key: Optional[str] = None,
    ) -> bool:
        """Store RSS feed entry with enhanced metadata."""
        try:
            # Get entry URL for deduplication
            url = entry.get("link", "")
            if not url:
                return False

            # Generate unique ID
            entry_id = self._generate_entry_id(url)

            # Skip if already processed
            if entry_id in self.processed_entries:
                return False

            # Get full content if available
            content = entry.get("content", [{}])[0].get("value", "")
            if not content:
                content = entry.get("summary", "")

            # Clean content
            if content:
                soup = BeautifulSoup(content, "html.parser")
                content = soup.get_text(separator=" ", strip=True)

            # Skip if no meaningful content
            if not content:
                return False

            # Process tags/categories
            tags = [
                tag.get("term", "").strip()
                for tag in entry.get("tags", [])
                if tag.get("term")
            ]

            # Extract any mentioned companies
            mentioned_companies = self._extract_company_mentions(
                f"{entry.get('title', '')} {content}"
            )

            # Store entry with enhanced metadata
            await self.store_raw_content(
                content_type="press_release",
                identifier=entry_id,
                raw_content={
                    "title": entry.get("title", ""),
                    "content": content,
                    "url": url,
                    "feed_url": feed_url,
                    "author": entry.get("author", ""),
                    "tags": tags,
                },
                metadata={
                    "symbol": company["symbol"],
                    "company_name": company["name"],
                    "sector": company["sector"],
                    "published_at": published.isoformat(),
                    "scraped_at": datetime.now().isoformat(),
                    "mentioned_companies": mentioned_companies,
                    "api_key_used": api_key,
                },
            )

            self.processed_entries.add(entry_id)
            return True

        except Exception as e:
            logger.error(f"[RSS] Error storing entry {entry.get('link')}: {str(e)}")
            return False

    def _extract_company_mentions(self, text: str) -> List[Dict]:
        """Extract mentions of other companies in the text."""
        mentions = []
        companies = get_all_companies()

        text = text.lower()
        for company in companies:
            # Only match exact symbols with word boundaries
            symbol_pattern = r"\b" + company["symbol"].lower() + r"\b"
            symbol_matches = list(re.finditer(symbol_pattern, text))
            symbol_mentions = len(symbol_matches)

            # Match company names
            name_mentions = text.count(company["name"].lower())

            if symbol_mentions > 0 or name_mentions > 0:
                # Get the first position of mention
                first_pos = float("inf")
                if symbol_mentions > 0:
                    first_pos = min(m.start() for m in symbol_matches)
                if name_mentions > 0:
                    name_pos = text.find(company["name"].lower())
                    if name_pos >= 0:
                        first_pos = min(first_pos, name_pos)

                mentions.append(
                    {
                        "symbol": company["symbol"],
                        "name": company["name"],
                        "mentions": {"symbol": symbol_mentions, "name": name_mentions},
                        "first_pos": first_pos,
                    }
                )

        # Sort by position of first mention
        mentions.sort(key=lambda x: x.pop("first_pos"))
        return mentions

    async def close(self):
        """Cleanup any resources."""
        pass
