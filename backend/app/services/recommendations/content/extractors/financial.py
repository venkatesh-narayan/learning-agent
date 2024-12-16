import logging
import time
from datetime import datetime
from typing import Optional, Tuple
from urllib.parse import urlparse

from app.models.recommendations.content import (
    ContentAnalysisResponse,
    ProcessedContent,
)
from app.prompts import PROMPTS
from app.services.recommendations.cache.openai_cache import OpenAICache
from bs4 import BeautifulSoup
from newspaper import Article
from openai import AsyncOpenAI
from readability import Document

logger = logging.getLogger(__name__)


class FinancialContentExtractor:
    """Extract financially relevant information from content."""

    def __init__(self, mongodb_uri: str, model: str = "gpt-4o"):
        self.client = AsyncOpenAI()
        self.model = model
        self.cache = OpenAICache(mongodb_uri)

    async def extract(
        self, content_id: str, url: str, html: str
    ) -> Optional[ProcessedContent]:
        """Extract financial insights from content."""
        try:
            # Get clean text and basic metadata
            logger.info(f"Extracting content from {url}")
            clean_text, metadata = await self._prepare_content(html, url)
            if not clean_text:
                return None

            # Extract all insights in single call
            logger.info(f"Analyzing content from {url}")
            analysis = await self._analyze_content(clean_text)

            return ProcessedContent(
                content_id=content_id,
                url=url,
                title=metadata["title"],
                source=metadata["source"],
                author=metadata.get("author"),
                publish_date=metadata["publish_date"],
                analysis=analysis,
            )

        except Exception as e:
            logger.error(f"Error extracting content from {url}: {str(e)}")
            return None

    async def _prepare_content(
        self, html: str, url: str
    ) -> Tuple[Optional[str], dict]:
        """Prepare content for extraction using readability and article parsing."""
        try:
            # Use readability for main content extraction
            doc = Document(html)
            readable_text = doc.summary()

            # Use newspaper for metadata
            article = Article(url)
            article.download(input_html=html)
            article.parse()

            # Clean up the text
            soup = BeautifulSoup(readable_text, "html.parser")
            clean_text = soup.get_text(separator="\n", strip=True)

            metadata = {
                "title": doc.title() or article.title,
                "source": urlparse(url).netloc,
                "author": article.authors[0] if article.authors else None,
                "publish_date": article.publish_date or datetime.now(),
            }

            return clean_text, metadata

        except Exception as e:
            logger.error(f"Error preparing content: {str(e)}")
            raise e

    async def _analyze_content(self, text: str) -> ContentAnalysisResponse:
        """Analyze content comprehensively in a single call."""
        try:
            messages = [
                {
                    "role": "system",
                    "content": PROMPTS["system"]["financial"][
                        "analyze_financial_content"
                    ],
                },
                {
                    "role": "user",
                    "content": PROMPTS["user"]["financial"][
                        "analyze_financial_content"
                    ].format(text=text),
                },
            ]

            start_time = time.time()

            # Check cache if available
            if self.cache:
                cached = await self.cache.get_cached_response(
                    messages=messages, model=self.model
                )
                if cached:
                    return ContentAnalysisResponse.model_validate(cached)

            response = await self.client.beta.chat.completions.parse(
                model=self.model,
                temperature=0,
                messages=messages,
                response_format=ContentAnalysisResponse,
            )

            # Store in cache if available
            if self.cache:
                duration_ms = int((time.time() - start_time) * 1000)
                await self.cache.store_call(
                    messages=messages,
                    model=self.model,
                    response=response.choices[0].message.parsed.model_dump(),
                    duration_ms=duration_ms,
                )

            return response.choices[0].message.parsed

        except Exception as e:
            logger.error(f"Error analyzing content: {str(e)}")
            raise e
