import asyncio
import logging
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

import aiohttp
from app.scripts.companies import get_all_companies, get_company_by_symbol
from app.scripts.rate_limiter import MultiAPIRateLimiter
from app.scripts.scrapers.base import BaseScraper

logger = logging.getLogger(__name__)


class EarningsCallScraper(BaseScraper):
    def __init__(
        self, api_keys: List[str], bucket_name: str = "scraped-financial-data"
    ):
        super().__init__(bucket_name)
        self.rate_limiter = MultiAPIRateLimiter(
            {
                "seeking_alpha": {
                    "keys": api_keys,
                    "calls_per_second": 2,  # Reduced from 5 to be more conservative
                    "calls_per_minute": 30,  # Reduced from 60 to be more conservative
                    "calls_per_day": 500,  # Per key limit
                }
            }
        )

        self.base_url = "https://seeking-alpha.p.rapidapi.com"
        self.headers_template = {"x-rapidapi-host": "seeking-alpha.p.rapidapi.com"}

        # Track processed transcripts to avoid duplicates
        self.processed_transcripts = set()

        # Track company assignments per API key
        self.key_company_assignments = defaultdict(set)

    def _generate_transcript_id(self, symbol: str, transcript_id: str) -> str:
        """Generate unique identifier for a transcript."""
        return f"earnings_{symbol}_{transcript_id}"

    def _assign_companies_to_keys(self, symbols: List[str]) -> Dict[str, List[str]]:
        """Distribute companies across API keys evenly."""
        assignments = defaultdict(list)
        for idx, symbol in enumerate(symbols):
            key = self.rate_limiter.limiters["seeking_alpha"].api_keys[
                idx % len(self.rate_limiter.limiters["seeking_alpha"].api_keys)
            ]
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
        max_per_company: int = 2,
        max_concurrent: int = 5,
        prioritize_sectors: Optional[List[str]] = None,
        **unused_kwargs,
    ) -> Dict[str, int]:
        """Scrape earnings call transcripts using multiple API keys in parallel."""
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
                logger.info(f"[EARNINGS] Prioritizing sectors: {prioritize_sectors}")
            symbols = [company["symbol"] for company in companies]
            logger.info(
                f"[EARNINGS] No symbols provided, using all {len(symbols)} companies"
            )

        results = defaultdict(int)
        company_assignments = self._assign_companies_to_keys(symbols)
        logger.info(
            f"[EARNINGS] Processing {len(symbols)} companies with "
            f"{len(self.rate_limiter.limiters['seeking_alpha'].api_keys)} API keys"
        )

        async with aiohttp.ClientSession() as session:
            tasks = []
            for api_key, assigned_symbols in company_assignments.items():
                for symbol_batch in self._batch_symbols(
                    assigned_symbols, max_concurrent
                ):
                    task = self._process_company_batch(
                        session=session,
                        symbols=symbol_batch,
                        api_key=api_key,
                        start_date=start_date,
                        max_per_company=max_per_company,
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
                    logger.error(f"[EARNINGS] Batch processing error: {str(result)}")

        logger.info(
            f"[EARNINGS] Scraping complete. Results by category: "
            f"{', '.join(f'{k}={v}' for k, v in results.items())}"
        )
        return dict(results)

    async def _process_company_batch(
        self,
        session: aiohttp.ClientSession,
        symbols: List[str],
        api_key: str,
        start_date: datetime,
        max_per_company: int,
    ) -> Dict[str, int]:
        """Process a batch of companies using a specific API key."""
        results = defaultdict(int)

        for symbol in symbols:
            try:
                company = get_company_by_symbol(symbol)

                # Get available transcripts
                headers = {
                    "x-rapidapi-host": "seeking-alpha.p.rapidapi.com",
                    "x-rapidapi-key": api_key,
                }

                await self.rate_limiter.acquire("seeking_alpha")

                # Add delay between requests
                await asyncio.sleep(1)

                async with session.get(
                    f"{self.base_url}/transcripts/v2/list",  # Changed to v2 endpoint
                    params={
                        "symbol": symbol,
                        "date_from": start_date.strftime("%Y-%m-%d"),
                    },
                    headers=headers,
                ) as response:
                    if response.status == 429:  # Rate limit
                        logger.warning(
                            f"[EARNINGS] Rate limit hit for {symbol}, waiting..."
                        )
                        await asyncio.sleep(30)  # Wait 30 seconds on rate limit
                        continue

                    if response.status == 403:  # Auth issue
                        logger.error(
                            f"[EARNINGS] Authentication failed for {symbol} - verify "
                            "RapidAPI key"
                        )
                        continue

                    if response.status == 204:  # No content
                        logger.info(f"[EARNINGS] No transcripts found for {symbol}")
                        continue

                    if response.status != 200:
                        logger.error(
                            f"[EARNINGS] Error fetching transcript list for {symbol}: "
                            f"{response.status}"
                        )
                        continue

                    transcript_list = await response.json()

                    # Sort by date and take most recent
                    available_transcripts = sorted(
                        transcript_list.get("data", []),
                        key=lambda x: x.get("date", ""),
                        reverse=True,
                    )[:max_per_company]

                    for transcript_meta in available_transcripts:
                        transcript_id = self._generate_transcript_id(
                            symbol, transcript_meta["id"]
                        )

                        if transcript_id in self.processed_transcripts:
                            continue

                        success = await self._scrape_transcript(
                            session=session,
                            company=company,
                            transcript_meta=transcript_meta,
                            transcript_id=transcript_id,
                            api_key=api_key,
                        )

                        if success:
                            results[company["sector"]] += 1
                            self.processed_transcripts.add(transcript_id)

                    # Small delay between companies
                    await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"[EARNINGS] Error processing {symbol}: {str(e)}")
                continue

        return results

    async def _fetch_transcript(
        self, session: aiohttp.ClientSession, symbol: str, api_key: str
    ) -> Optional[Dict]:
        """Fetch earnings call transcript."""
        try:
            url = f"{self.base_url}/get-earnings"
            headers = {**self.headers_template, "x-rapidapi-key": api_key}
            params = {"symbol": symbol, "sort": "date", "page": "1"}

            async with session.get(url, headers=headers, params=params) as response:
                if response.status == 401:
                    logger.error(
                        f"[EARNINGS] Authentication failed for {symbol} - verify "
                        "RapidAPI key"
                    )
                    return None
                elif response.status == 429:
                    logger.warning(
                        f"[EARNINGS] Rate limit hit for {symbol}, waiting..."
                    )
                    await asyncio.sleep(60)  # Wait for rate limit reset
                    return await self._fetch_transcript(
                        session, symbol, api_key
                    )  # Retry
                elif response.status != 200:
                    logger.error(
                        f"[EARNINGS] Error fetching transcript for {symbol}: "
                        f"{response.status}"
                    )
                    return None

                data = await response.json()
                if not data or not data.get("data"):
                    logger.warning(f"[EARNINGS] No transcript data found for {symbol}")
                    return None

                return data

        except Exception as e:
            logger.error(f"[EARNINGS] Error processing {symbol}: {str(e)}")
            return None

    async def _process_transcript(
        self,
        session: aiohttp.ClientSession,
        symbol: str,
        api_key: str,
    ) -> bool:
        """Process earnings call transcript."""
        try:
            data = await self._fetch_transcript(session, symbol, api_key)
            if not data:
                return False

            company = get_company_by_symbol(symbol)
            if not company:
                logger.error(f"[EARNINGS] Company not found for symbol {symbol}")
                return False

            # Store the transcript
            transcript_id = f"{symbol}_{data['data'][0]['id']}"
            if transcript_id in self.processed_transcripts:
                return True

            await self.store_raw_content(
                content_type="earnings_call",
                identifier=transcript_id,
                raw_content=data["data"][0],
                metadata={
                    "symbol": symbol,
                    "company_name": company["name"],
                    "sector": company["sector"],
                    "date": data["data"][0].get("date"),
                    "quarter": data["data"][0].get("quarter"),
                    "year": data["data"][0].get("year"),
                    "api_key_used": api_key,
                },
            )

            self.processed_transcripts.add(transcript_id)
            return True

        except Exception as e:
            logger.error(
                f"[EARNINGS] Error processing transcript for {symbol}: {str(e)}"
            )
            return False

    async def _make_request(
        self,
        session: aiohttp.ClientSession,
        url: str,
        api_key: str,
        params: Dict = None,
    ) -> dict:
        """Make a request to the Seeking Alpha API with improved error handling."""
        headers = {**self.headers_template, "x-rapidapi-key": api_key}

        try:
            async with self.rate_limiter.limiters["seeking_alpha"].acquire(api_key):
                async with session.get(
                    url, headers=headers, params=params
                ) as response:
                    if response.status == 401:
                        error_msg = (
                            "[EARNINGS] Authentication failed - verify RapidAPI key: "
                            f"{api_key[:8]}..."
                        )
                        logger.error(error_msg)
                        raise ValueError(error_msg)
                    elif response.status == 429:
                        error_msg = "[EARNINGS] Rate limit exceeded, waiting..."
                        logger.warning(error_msg)
                        await asyncio.sleep(30)  # Wait 30 seconds before retry
                        raise RuntimeError(error_msg)
                    elif response.status != 200:
                        error_msg = (
                            "[EARNINGS] API request failed with status "
                            f"{response.status}"
                        )
                        logger.error(error_msg)
                        raise RuntimeError(error_msg)

                    return await response.json()

        except aiohttp.ClientError as e:
            logger.error(f"[EARNINGS] Network error: {str(e)}")
            raise
        except asyncio.TimeoutError:
            logger.error("[EARNINGS] Request timed out")
            raise
        except Exception as e:
            logger.error(
                f"[EARNINGS] Unexpected error: {e.__class__.__name__}: {str(e)}"
            )
            raise

    async def _scrape_transcript(
        self,
        session: aiohttp.ClientSession,
        company: Dict,
        transcript_meta: Dict,
        transcript_id: str,
        api_key: str,
    ) -> bool:
        """Scrape individual transcript."""
        try:
            url = f"{self.base_url}/transcripts/v2/get"
            params = {"id": transcript_meta["id"]}
            transcript_data = await self._make_request(session, url, api_key, params)

            sections = await self._extract_sections(transcript_data)

            await self.store_raw_content(
                content_type="earnings_call",
                identifier=transcript_id,
                raw_content={
                    "raw_transcript": transcript_data,
                    "extracted_sections": sections,
                },
                metadata={
                    "symbol": company["symbol"],
                    "company_name": company["name"],
                    "sector": company["sector"],
                    "call_date": transcript_meta.get("date"),
                    "quarter": transcript_meta.get("fiscal_quarter"),
                    "year": transcript_meta.get("fiscal_year"),
                    "source": "seeking_alpha",
                    "api_key_used": api_key,
                },
            )

            return True

        except Exception as e:
            logger.error(
                f"[EARNINGS] Error scraping transcript {transcript_meta.get('id')}: "
                f"{str(e)}"
            )
            return False

    def _extract_speaker_segments(self, text: str) -> List[Dict]:
        """Extract individual speaker segments from presentation text."""
        segments = []
        current_segment = None

        # Simple speaker pattern: "Speaker Name:"
        for line in text.split("\n"):
            if ":" in line and len(line.split(":")[0].split()) <= 5:
                # Likely a new speaker
                if current_segment:
                    segments.append(current_segment)

                speaker = line.split(":")[0].strip()
                content = line.split(":", 1)[1].strip()
                current_segment = {"speaker": speaker, "content": content}
            elif current_segment:
                current_segment["content"] += " " + line.strip()

        # Add the last segment
        if current_segment:
            segments.append(current_segment)

        return segments

    def _extract_qa_segments(self, text: str) -> List[Dict]:
        """Extract Q&A segments with question-answer pairs."""
        segments = []
        current_segment = None

        for line in text.split("\n"):
            if ":" in line and len(line.split(":")[0].split()) <= 5:
                speaker = line.split(":")[0].strip()
                content = line.split(":", 1)[1].strip()

                # Check if this is a new question (usually from an analyst)
                if "?" in content or speaker.lower().endswith("analyst"):
                    # Save previous segment if exists
                    if current_segment:
                        segments.append(current_segment)

                    current_segment = {
                        "question": {"speaker": speaker, "content": content},
                        "answers": [],
                    }
                elif current_segment:
                    # This is an answer
                    current_segment["answers"].append(
                        {"speaker": speaker, "content": content}
                    )
            elif current_segment:
                # Continue previous speaker's content
                if current_segment["answers"]:
                    current_segment["answers"][-1]["content"] += " " + line.strip()
                else:
                    current_segment["question"]["content"] += " " + line.strip()

        # Add the last segment
        if current_segment:
            segments.append(current_segment)

        return segments

    async def _extract_sections(self, transcript_data: Dict) -> List[Dict]:
        """Extract sections from transcript data with enhanced structure."""
        sections = []

        # Add participant information
        if "participants" in transcript_data:
            sections.append(
                {
                    "title": "Participants",
                    "content": str(transcript_data["participants"]),
                    "type": "participants",
                    "metadata": {
                        "executives": [
                            p
                            for p in transcript_data.get("participants", [])
                            if p.get("role", "").lower() == "executive"
                        ],
                        "analysts": [
                            p
                            for p in transcript_data.get("participants", [])
                            if p.get("role", "").lower() == "analyst"
                        ],
                    },
                }
            )

        # Add prepared remarks
        if "presentation" in transcript_data:
            sections.append(
                {
                    "title": "Management Presentation",
                    "content": transcript_data["presentation"],
                    "type": "presentation",
                    "metadata": {
                        "speaker_segments": self._extract_speaker_segments(
                            transcript_data["presentation"]
                        )
                    },
                }
            )

        # Add Q&A session
        if "qa_session" in transcript_data:
            sections.append(
                {
                    "title": "Q&A Session",
                    "content": transcript_data["qa_session"],
                    "type": "qa",
                    "metadata": {
                        "qa_segments": self._extract_qa_segments(
                            transcript_data["qa_session"]
                        )
                    },
                }
            )

        return sections

    async def close(self):
        """Cleanup any resources."""
        pass
