import logging
import time
from typing import List

from app.models.recommendations.query_lines import QueryLine
from app.prompts import PROMPTS
from app.services.recommendations.cache.openai_cache import OpenAICache
from openai import AsyncOpenAI
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class QueryLineGrouper:
    """Groups related query lines together for knowledge state analysis."""

    def __init__(self, mongodb_uri: str, model: str = "gpt-4o"):
        self.client = AsyncOpenAI()
        self.model = model
        self.cache = OpenAICache(mongodb_uri)

    async def get_related_lines(
        self,
        current_line: QueryLine,
        all_lines: List[QueryLine],
    ) -> List[QueryLine]:
        """Find query lines related to the current line."""

        class IndicesList(BaseModel):
            indices: List[int]

        try:
            if len(all_lines) <= 1:
                return [current_line]

            # Format line contexts
            lines_context = []
            for line in all_lines:
                if line != current_line:
                    line_info = []
                    line_info.append(f"Topic: {line.line_topic}")
                    line_info.append("Queries:")
                    for query in line.queries:
                        line_info.append(f"- {query}")
                    lines_context.append("\n".join(line_info))

            current_info = [
                f"Current Topic: {current_line.line_topic}",
                "Queries:",
                *[f"- {q}" for q in current_line.queries],
            ]

            messages = [
                {
                    "role": "system",
                    "content": PROMPTS["system"]["query_lines"]["group_lines"],
                },
                {
                    "role": "user",
                    "content": PROMPTS["user"]["query_lines"]["group_lines"].format(
                        current_line="\n".join(current_info),
                        other_lines="\n\n".join(lines_context),
                    ),
                },
            ]

            start_time = time.time()

            # Check cache
            cached = await self.cache.get_cached_response(
                messages=messages, model=self.model
            )
            if cached:
                result = IndicesList.model_validate(cached)
            else:
                response = await self.client.beta.chat.completions.parse(
                    model=self.model,
                    temperature=0,
                    messages=messages,
                    response_format=IndicesList,
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

            related_indices = result.indices

            # Convert indices back to lines
            related_lines = [all_lines[i] for i in related_indices]
            if current_line not in related_lines:
                related_lines.append(current_line)

            logger.info(
                f"Found {len(related_lines)} related lines for topic "
                f"{current_line.line_topic}"
            )

            return related_lines

        except Exception as e:
            logger.error(f"Error grouping query lines: {str(e)}")
            return [current_line]
