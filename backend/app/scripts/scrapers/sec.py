import asyncio
import logging
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

import aiohttp
from app.scripts.companies import get_all_companies, get_company_by_symbol
from app.scripts.rate_limiter import MultiAPIRateLimiter
from app.scripts.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class SECFilingScraper(BaseScraper):
    def __init__(
        self,
        user_agents: List[str],  # Multiple user agents required by SEC
        bucket_name: str = "scraped-financial-data",
    ):
        super().__init__(bucket_name)
        self.user_agents = user_agents
        self.rate_limiter = MultiAPIRateLimiter(
            {
                "sec": {
                    "keys": user_agents,
                    "calls_per_second": 1,  # Even more conservative rate limiting
                    "calls_per_day": 10000,  # Per key limit
                }
            }
        )

        # Filing types we're interested in
        self.filing_types = {"10-K", "10-Q", "8-K"}
        self.base_urls = {
            "company": "https://data.sec.gov/submissions/CIK{cik}.json",
            "filing": "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}",
        }

        # Track processed filings to avoid duplicates
        self.processed_filings = set()

        # Track which companies each API key has processed
        self.key_company_assignments = defaultdict(set)

    def _generate_filing_id(self, cik: str, accession: str, form_type: str) -> str:
        """Generate unique identifier for a filing."""
        return f"sec_{cik}_{accession}_{form_type}"

    def _assign_companies_to_keys(self, symbols: List[str]) -> Dict[str, List[str]]:
        """Distribute companies across API keys evenly."""
        assignments = defaultdict(list)
        for idx, symbol in enumerate(symbols):
            key = self.user_agents[idx % len(self.user_agents)]
            assignments[key].append(symbol)
        return assignments

    async def scrape(
        self,
        start_date: datetime,
        end_date: Optional[datetime] = None,
        symbols: Optional[List[str]] = None,
        filing_types: Optional[Set[str]] = None,
        max_concurrent: int = 1,  # Reduced concurrency
        **unused_kwargs,
    ) -> Dict[str, int]:
        """Scrape SEC filings using multiple API keys in parallel."""
        if not symbols:
            symbols = [company["symbol"] for company in get_all_companies()]
            logger.info(
                f"[SEC] No symbols provided, using all {len(symbols)} companies"
            )
        if not filing_types:
            filing_types = self.filing_types
            logger.info(f"[SEC] Using default filing types: {filing_types}")
        if not end_date:
            end_date = datetime.now()

        results = defaultdict(int)
        company_assignments = self._assign_companies_to_keys(symbols)
        logger.info(
            f"[SEC] Processing {len(symbols)} companies with {len(self.user_agents)} "
            "user agents"
        )

        async with aiohttp.ClientSession() as session:
            # Process companies in parallel for each API key
            tasks = []
            for user_agent, assigned_symbols in company_assignments.items():
                for symbol_batch in self._batch_symbols(
                    assigned_symbols, max_concurrent
                ):
                    task = self._process_company_batch(
                        session=session,
                        symbols=symbol_batch,
                        user_agent=user_agent,
                        start_date=start_date,
                        end_date=end_date,
                        filing_types=filing_types,
                    )
                    tasks.append(task)

            # Wait for all tasks to complete
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Aggregate results with improved error handling
            for result in batch_results:
                if isinstance(result, dict):
                    for category, count in result.items():
                        results[category] += count
                elif isinstance(result, Exception):
                    logger.error(f"[SEC] Batch processing error: {str(result)}")

        logger.info(
            f"[SEC] Scraping complete. Results by filing type: "
            f"{', '.join(f'{k}={v}' for k, v in results.items())}"
        )
        return dict(results)

    def _batch_symbols(self, symbols: List[str], batch_size: int) -> List[List[str]]:
        """Split symbols into batches for parallel processing."""
        return [
            symbols[i : i + batch_size]  # noqa
            for i in range(0, len(symbols), batch_size)
        ]

    async def _process_company_batch(
        self,
        session: aiohttp.ClientSession,
        symbols: List[str],
        user_agent: str,
        start_date: datetime,
        end_date: datetime,
        filing_types: Set[str],
    ) -> Dict[str, int]:
        """Process a batch of companies using a specific API key."""
        results = defaultdict(int)

        for symbol in symbols:
            try:
                company = get_company_by_symbol(symbol)
                if not company:
                    logger.error(f"[SEC] Company not found for symbol {symbol}")
                    continue

                cik = company.get("cik")
                if not cik:
                    logger.error(f"[SEC] No CIK found for {symbol}")
                    continue

                # Pad CIK to 10 digits as required by SEC
                cik = str(cik).zfill(10)

                # Get company filings
                url = self.base_urls["company"].format(cik=cik)
                headers = {"User-Agent": user_agent}

                async with session.get(url, headers=headers) as response:
                    if response.status == 404:
                        logger.error(
                            f"[SEC] No filings found for {symbol} (CIK: {cik})"
                        )
                        continue
                    elif response.status == 403:
                        logger.error(
                            f"[SEC] Access denied for {symbol} - check user agent"
                        )
                        continue
                    elif response.status != 200:
                        logger.error(
                            f"[SEC] Error fetching filings for {symbol}: "
                            f"{response.status}"
                        )
                        continue

                    data = await response.json()
                    if not data or not data.get("filings"):
                        logger.error(f"[SEC] Empty or invalid response for {symbol}")
                        continue

                    # Process recent filings
                    recent_filings = data["filings"]["recent"]
                    filing_tasks = []

                    for idx, form in enumerate(recent_filings["form"]):
                        if form not in filing_types:
                            continue

                        filing_date = datetime.strptime(
                            recent_filings["filingDate"][idx], "%Y-%m-%d"
                        )
                        if not (start_date <= filing_date <= end_date):
                            continue

                        accession = recent_filings["accessionNumber"][idx].replace(
                            "-", ""
                        )
                        primary_doc = recent_filings["primaryDocument"][idx]
                        filing_id = self._generate_filing_id(cik, accession, form)

                        if filing_id in self.processed_filings:
                            continue

                        filing_tasks.append(
                            self._scrape_filing(
                                session=session,
                                company=company,
                                cik=cik,
                                accession=accession,
                                primary_doc=primary_doc,
                                form_type=form,
                                filing_date=filing_date,
                                filing_id=filing_id,
                                user_agent=user_agent,
                            )
                        )

                    # Process filings concurrently
                    filing_results = await asyncio.gather(
                        *filing_tasks, return_exceptions=True
                    )
                    for result in filing_results:
                        if isinstance(result, tuple) and not isinstance(
                            result, Exception
                        ):
                            form_type, success = result
                            if success:
                                results[form_type] += 1

                # Small delay between companies
                await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"[SEC] Error processing {symbol}: {str(e)}")
                continue

        return dict(results)

    async def _scrape_filing(
        self,
        session: aiohttp.ClientSession,
        company: Dict,
        cik: str,
        accession: str,
        primary_doc: str,
        form_type: str,
        filing_date: datetime,
        filing_id: str,
        user_agent: str,
    ) -> Tuple[str, bool]:
        """Scrape individual filing."""
        filing_url = ""
        try:
            filing_url = (
                self.base_urls["filing"].format(cik=cik, accession=accession)
                + f"/{primary_doc}"
            )

            key = await self.rate_limiter.acquire("sec")
            if not key:
                return form_type, False

            async with session.get(
                filing_url, headers={"User-Agent": key}
            ) as response:
                if response.status != 200:
                    logger.error(
                        f"[SEC] Error fetching {form_type} {filing_url}: "
                        f"{response.status}"
                    )
                    return form_type, False

                content = await response.text()

                # Store raw content with safe sector handling
                await self.store_raw_content(
                    content_type="sec_filing",
                    identifier=filing_id,
                    raw_content={
                        "url": filing_url,
                        "filing_type": form_type,
                        "filing_html": content,
                    },
                    metadata={
                        "symbol": company.get("symbol", ""),
                        "company_name": company.get("name", ""),
                        "sector": company.get("sector", "Unknown"),
                        "filing_type": form_type,
                        "filing_date": filing_date.isoformat(),
                        "cik": cik,
                        "accession": accession,
                        "api_key_used": user_agent,
                    },
                )

                self.processed_filings.add(filing_id)
                logger.info(
                    f"[SEC] Successfully processed {form_type} filing for "
                    f"{company.get('name', '')} ({company.get('symbol', '')})"
                )
                return form_type, True

        except Exception as e:
            logger.error(f"[SEC] Error scraping filing {filing_url}: {str(e)}")
            return form_type, False

    async def close(self):
        """Close any open resources."""
        pass
