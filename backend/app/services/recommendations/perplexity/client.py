import logging
import time
from datetime import datetime
from typing import List, Optional, Tuple

import aiohttp
from app.models.recommendations.query_lines import QueryLine
from app.services.recommendations.cache.perplexity_cache import PerplexityCache

logger = logging.getLogger(__name__)


class PerplexityClient:
    """Client for getting Perplexity responses and updating query lines."""

    def __init__(
        self,
        api_key: str,
        mongodb_uri: str,
        model: str = "llama-3.1-sonar-large-128k-online",
        request_timeout: int = 30,
    ):
        self.api_key = api_key
        self.model = model
        self.timeout = request_timeout
        self.cache = PerplexityCache(mongodb_uri)

    async def get_response(
        self, query: str, query_line: Optional[QueryLine] = None
    ) -> Tuple[str, List[str], Optional[QueryLine]]:
        """
        Get response from Perplexity and optionally update query line.

        Args:
            query: The user's query
            query_line: QueryLine to update with response (if provided)

        Returns:
            Tuple of (response_text, updated_query_line)
        """
        try:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "Be specific and precise. Follow every detail in the user query."  # noqa: E501
                    ),
                },
            ]

            if query_line is not None:
                # Include previous context if available
                for q, a in zip(query_line.queries[:-1], query_line.responses):
                    messages.append({"role": "user", "content": q})
                    messages.append({"role": "assistant", "content": a})

            # Add current query
            messages.append({"role": "user", "content": query})

            start_time = time.time()

            # Check cache first
            cached = await self.cache.get_cached_response(
                messages=messages, model=self.model
            )

            if cached:
                answer = (
                    cached.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                )
                citations = cached.get("citations", [])
                logger.info("Using cached Perplexity response")
            else:
                # Get response from Perplexity
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        "https://api.perplexity.ai/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "model": self.model,
                            "messages": messages,
                            "temperature": 0,
                        },
                        timeout=self.timeout,
                    ) as response:
                        if response.status != 200:
                            error = f"Perplexity API error: {response.status}"
                            logger.error(error)
                            raise Exception(error)

                        data = await response.json()
                        answer = (
                            data.get("choices", [{}])[0]
                            .get("message", {})
                            .get("content", "")
                        )
                        citations = data.get("citations", [])

                        # Cache the response
                        duration_ms = int((time.time() - start_time) * 1000)
                        await self.cache.store_call(
                            messages=messages,
                            model=self.model,
                            response=data,
                            citations=citations,
                            duration_ms=duration_ms,
                        )

                        logger.info(
                            f"Got new Perplexity response with {len(citations)} "
                            "citations"
                        )

            # Update query line if provided
            if query_line is not None:
                query_line.responses.append(answer)
                query_line.timestamps.append(datetime.now())
                query_line.last_updated = datetime.now()
                logger.info(f"Updated query line {query_line.line_topic}")

            return answer, citations, query_line

        except Exception as e:
            logger.error(f"Error getting Perplexity response: {str(e)}")
            raise
