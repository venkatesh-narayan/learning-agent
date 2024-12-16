import logging
import time
import uuid
from datetime import datetime
from typing import List, Tuple

from app.models.recommendations.query_lines import (
    LineAnalysis,
    LineAnalysisWithTopic,
    QueryLine,
    QueryLineContext,
)
from app.prompts import PROMPTS
from app.services.recommendations.cache.openai_cache import OpenAICache
from motor.motor_asyncio import AsyncIOMotorClient
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class QueryLineManager:
    """Manages query lines and their analysis."""

    def __init__(self, mongodb_uri: str, model: str = "gpt-4o"):
        """Initialize with database and LLM configuration."""
        self.client = AsyncIOMotorClient(mongodb_uri)
        self.db = self.client.recommendations
        self.llm_client = AsyncOpenAI()
        self.model = model
        self.cache = OpenAICache(mongodb_uri)

        self._ensure_indexes()

    def _ensure_indexes(self):
        """Create necessary database indexes."""
        # Primary index on user_id and last_updated for efficient retrieval
        self.db.query_lines.create_index([("user_id", 1), ("last_updated", -1)])
        # Secondary index on topic for searching
        self.db.query_lines.create_index([("user_id", 1), ("line_topic", 1)])

    async def get_or_update_line(
        self, user_id: str, query: str
    ) -> Tuple[QueryLine, LineAnalysis]:
        """Get existing line or create new one, then analyze it."""
        # Get existing lines for user
        existing_lines = await self._get_user_lines(user_id, limit=100)

        # Detect if this continues a line
        line_context = await self._detect_line_context(query, existing_lines)

        # Get or create appropriate line
        if line_context.continues_line:
            line = existing_lines[line_context.line_index]
            original_topic = line.line_topic  # Store original topic
            line.queries.append(query)
            line.timestamps.append(datetime.now())
            line.last_updated = datetime.now()
            await self._update_line(line, original_topic)
        else:
            line = QueryLine(
                user_id=user_id,
                line_id=str(uuid.uuid4()),  # Generate UUID for new lines
                queries=[query],
                timestamps=[datetime.now()],
                responses=[],
                line_topic=query,  # Initial topic, will be refined
                last_updated=datetime.now(),
            )
            await self._store_line(line)
            logger.info("Created new query line")

        # Analyze the complete line and potentially update topic
        analysis, refined_topic = await self.analyze_line(line)

        # Update topic if it changed
        if refined_topic != line.line_topic:
            original_topic = line.line_topic  # Store original topic
            line.line_topic = refined_topic
            await self._update_line(line, original_topic)
            logger.info(
                f"Updated line topic from '{original_topic}' to '{refined_topic}'"
            )

        return line, analysis

    async def _detect_line_context(
        self, query: str, existing_lines: List[QueryLine]
    ) -> QueryLineContext:
        """Determine if query continues an existing line."""
        try:
            # Format lines info properly
            lines_context = []
            for line in existing_lines:
                formatted_line = f"Line Topic: {line.line_topic}\nPrevious Queries:\n"
                formatted_line += "\n".join(
                    f"- Q: {q}\n  A: {r}" for q, r in zip(line.queries, line.responses)
                )
                lines_context.append(formatted_line)

            formatted_context = "\n\n".join(lines_context)

            messages = [
                {
                    "role": "system",
                    "content": PROMPTS["system"]["query_lines"]["detect_line"],
                },
                {
                    "role": "user",
                    "content": PROMPTS["user"]["query_lines"]["detect_line"].format(
                        existing_lines=formatted_context, current_query=query
                    ),
                },
            ]

            start_time = time.time()

            # Check cache
            cached = await self.cache.get_cached_response(
                messages=messages, model=self.model
            )
            if cached:
                return QueryLineContext.model_validate(cached)

            response = await self.llm_client.beta.chat.completions.parse(
                model=self.model,
                temperature=0,
                messages=messages,
                response_format=QueryLineContext,
            )

            result = response.choices[0].message.parsed

            # Store in cache
            duration_ms = int((time.time() - start_time) * 1000)
            await self.cache.store_call(
                messages=messages,
                model=self.model,
                response=result.model_dump(),
                duration_ms=duration_ms,
            )

            return result

        except Exception as e:
            logger.error(f"Error detecting line context: {e}")
            raise

    async def analyze_line(self, line: QueryLine) -> Tuple[LineAnalysis, str]:
        """Analyze a complete query line and determine refined topic."""
        try:
            if len(line.queries) > 1:
                previous_queries = "\n".join([f"- {q}" for q in line.queries[:-1]])
            else:
                previous_queries = ""

            messages = [
                {
                    "role": "system",
                    "content": PROMPTS["system"]["query_lines"]["analyze_line"],
                },
                {
                    "role": "user",
                    "content": PROMPTS["user"]["query_lines"]["analyze_line"].format(
                        query=line.queries[-1], previous_queries=previous_queries
                    ),
                },
            ]

            start_time = time.time()

            # Check cache
            cached = await self.cache.get_cached_response(
                messages=messages, model=self.model
            )
            if cached:
                result = LineAnalysisWithTopic.model_validate(cached)
                return result.analysis, result.refined_topic

            response = await self.llm_client.beta.chat.completions.parse(
                model=self.model,
                temperature=0,
                messages=messages,
                response_format=LineAnalysisWithTopic,
            )

            result = response.choices[0].message.parsed

            # Store in cache
            duration_ms = int((time.time() - start_time) * 1000)
            await self.cache.store_call(
                messages=messages,
                model=self.model,
                response=result.model_dump(),
                duration_ms=duration_ms,
            )

            return result.analysis, result.refined_topic

        except Exception as e:
            logger.error(f"Error analyzing line: {e}")
            raise

    async def _get_user_lines(self, user_id: str, limit: int = 5) -> List[QueryLine]:
        """Get user's recent query lines."""
        cursor = (
            self.db.query_lines.find({"user_id": user_id})
            .sort("last_updated", -1)
            .limit(limit)
        )
        lines = []
        async for doc in cursor:
            try:
                lines.append(QueryLine(**doc))
            except Exception as e:
                logger.error(f"Error parsing query line: {e}")
        return lines

    async def _store_line(self, line: QueryLine) -> None:
        """Store a new query line."""
        try:
            await self.db.query_lines.insert_one(line.model_dump())
            logger.info(
                f"Stored new line for user {line.user_id} with topic {line.line_topic}"
            )
        except Exception as e:
            logger.error(f"Error storing line: {e}")
            raise

    async def _update_line(self, line: QueryLine, original_topic: str = None) -> None:
        """Update an existing query line."""
        try:
            # Add debug logging
            logger.info(f"Updating line with topic {line.line_topic}...")

            # Use user_id and line_id for updates, not topic
            query = {"user_id": line.user_id}
            if hasattr(line, "line_id"):
                query["line_id"] = line.line_id
            else:
                # Fallback to using original topic if no line_id
                query["line_topic"] = original_topic or line.line_topic

            result = await self.db.query_lines.replace_one(query, line.model_dump())

            if result.matched_count == 0:
                logger.error(f"No line found to update for user {line.user_id}")
            else:
                logger.info(
                    f"Updated line for user {line.user_id} topic {line.line_topic}"
                )
        except Exception as e:
            logger.error(f"Error updating line: {e}")
            raise
