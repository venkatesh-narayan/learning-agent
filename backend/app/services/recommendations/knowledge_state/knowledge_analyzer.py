import logging
import time
from typing import Dict, List

from app.models.recommendations.knowledge_state import KnowledgeState
from app.models.recommendations.query_lines import QueryLine
from app.prompts import PROMPTS
from app.services.recommendations.cache.openai_cache import OpenAICache
from openai import AsyncOpenAI
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class KnowledgeAnalyzer:
    """Analyzes user knowledge and learning state across query lines."""

    def __init__(self, mongodb_uri: str, model: str = "gpt-4o"):
        self.client = AsyncOpenAI()
        self.model = model
        self.cache = OpenAICache(mongodb_uri)

    async def analyze_knowledge(
        self,
        current_line: QueryLine,
        related_lines: List[QueryLine],
    ) -> KnowledgeState:
        """
        Analyze knowledge state across query lines.
        Distinguishes between demonstrated knowledge and exposed information.
        """
        try:
            # Format current line's queries and responses
            current_interactions = []
            for q, r in zip(current_line.queries[:-1], current_line.responses):
                current_interactions.extend(
                    [{"type": "query", "text": q}, {"type": "response", "text": r}]
                )
            # Add latest query without response
            current_interactions.append(
                {"type": "query", "text": current_line.queries[-1]}
            )

            # Format related lines
            related_interactions = []
            for line in related_lines:
                if line != current_line:
                    line_interactions = []
                    for q, r in zip(line.queries, line.responses):
                        line_interactions.extend(
                            [
                                {"type": "query", "text": q},
                                {"type": "response", "text": r},
                            ]
                        )
                    related_interactions.append(
                        {"topic": line.line_topic, "interactions": line_interactions}
                    )

            messages = [
                {
                    "role": "system",
                    "content": PROMPTS["system"]["knowledge_state"]["analyze_state"],
                },
                {
                    "role": "user",
                    "content": PROMPTS["user"]["knowledge_state"][
                        "analyze_state"
                    ].format(
                        current_topic=current_line.line_topic,
                        current_interactions=self._format_interactions(
                            current_interactions
                        ),
                        related_interactions=self._format_related_interactions(
                            related_interactions
                        ),
                    ),
                },
            ]

            start_time = time.time()

            # Check cache
            cached = await self.cache.get_cached_response(
                messages=messages, model=self.model
            )
            if cached:
                state = KnowledgeState.model_validate(cached)
            else:
                response = await self.client.beta.chat.completions.parse(
                    model=self.model,
                    temperature=0,
                    messages=messages,
                    response_format=KnowledgeState,
                )
                state = response.choices[0].message.parsed

                # Store in cache
                duration_ms = int((time.time() - start_time) * 1000)
                await self.cache.store_call(
                    messages=messages,
                    model=self.model,
                    response=state.model_dump(),
                    duration_ms=duration_ms,
                )

            # Extract concepts from latest response if it exists
            if current_line.responses:
                latest_concepts = await self._extract_response_concepts(
                    current_line.responses[-1]
                )
                state.current_topic.latest_response_concepts = latest_concepts

            return state

        except Exception as e:
            logger.error(f"Error analyzing knowledge state: {str(e)}")
            raise

    async def _extract_response_concepts(self, response: str) -> List[str]:
        """Extract key concepts from a response."""
        try:
            messages = [
                {
                    "role": "system",
                    "content": PROMPTS["system"]["knowledge_state"][
                        "extract_concepts"
                    ],
                },
                {
                    "role": "user",
                    "content": PROMPTS["user"]["knowledge_state"][
                        "extract_concepts"
                    ].format(response=response),
                },
            ]

            class ConceptList(BaseModel):
                concepts: List[str]

            # Check cache
            cached = await self.cache.get_cached_response(
                messages=messages, model=self.model
            )
            if cached:
                return ConceptList.model_validate(cached).concepts

            response = await self.client.beta.chat.completions.parse(
                model=self.model,
                temperature=0,
                messages=messages,
                response_format=ConceptList,
            )

            concepts = response.choices[0].message.parsed.concepts

            # Store in cache
            await self.cache.store_call(
                messages=messages,
                model=self.model,
                response={"concepts": concepts},
            )

            return concepts

        except Exception as e:
            logger.error(f"Error extracting response concepts: {str(e)}")
            return []

    def _format_interactions(self, interactions: List[Dict]) -> str:
        """Format a list of interactions for analysis."""
        formatted = ["Interactions:"]
        for interaction in interactions:
            prefix = "Q:" if interaction["type"] == "query" else "A:"
            formatted.append(f"{prefix} {interaction['text']}")
        return "\n".join(formatted)

    def _format_related_interactions(self, related_interactions: List[Dict]) -> str:
        """Format related interactions for analysis."""
        if not related_interactions:
            return "No related interactions"

        formatted = []
        for line in related_interactions:
            formatted.extend(
                [
                    f"\nTopic: {line['topic']}",
                    self._format_interactions(line["interactions"]),
                ]
            )
        return "\n".join(formatted)
