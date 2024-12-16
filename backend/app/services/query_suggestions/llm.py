from typing import Any, Dict, List

from app.models.learning import TopicKnowledge
from app.models.query import QueryAnalysis, SuggestionsResponse, UserContext
from app.prompts import PROMPTS
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential


class LLMService:
    def __init__(self, api_key: str, model: str):
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = model

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True,
    )
    async def _make_completion(
        self, messages: List[Dict[str, str]], response_format: Any
    ) -> Any:
        """Make an API call to OpenAI with retry logic."""
        completion = await self.client.beta.chat.completions.parse(
            model=self.model,
            temperature=0,
            messages=messages,
            response_format=response_format,
        )
        return completion.choices[0].message.parsed

    async def analyze_query(
        self, query: str, user_context: UserContext
    ) -> QueryAnalysis:
        """Analyze query intent and context."""
        recent_queries = "\n".join(
            [f"- {q.text}" for q in user_context.recent_queries[-5:]]
        )

        messages = [
            {
                "role": "system",
                "content": PROMPTS["system"]["query_suggestions"]["analyze_query"],
            },
            {
                "role": "user",
                "content": PROMPTS["user"]["query_suggestions"][
                    "analyze_query"
                ].format(query=query, recent_queries=recent_queries),
            },
        ]

        return await self._make_completion(messages, QueryAnalysis)

    async def assess_topic_knowledge(
        self, topic: str, queries: List[str], current_knowledge: Dict
    ) -> TopicKnowledge:
        """Assess user's knowledge in a specific topic."""
        messages = [
            {
                "role": "system",
                "content": PROMPTS["system"]["query_suggestions"]["assess_knowledge"],
            },
            {
                "role": "user",
                "content": PROMPTS["user"]["query_suggestions"][
                    "assess_knowledge"
                ].format(
                    topic=topic,
                    queries="\n".join(f"- {q}" for q in queries),
                    current_knowledge=current_knowledge or {},
                ),
            },
        ]

        return await self._make_completion(messages, TopicKnowledge)

    async def generate_suggestions(
        self,
        query: str,
        topic: str,
        known_concepts: List[str],
        knowledge_gaps: List[str],
        recommended_topics: List[str],
    ) -> SuggestionsResponse:
        """Generate personalized query suggestions."""
        messages = [
            {
                "role": "system",
                "content": PROMPTS["system"]["query_suggestions"][
                    "generate_suggestions"
                ],
            },
            {
                "role": "user",
                "content": PROMPTS["user"]["query_suggestions"][
                    "generate_suggestions"
                ].format(
                    query=query,
                    topic=topic,
                    known_concepts=known_concepts,
                    gaps=knowledge_gaps,
                    recommended_topics=recommended_topics,
                ),
            },
        ]

        return await self._make_completion(messages, SuggestionsResponse)

    async def close(self):
        await self.client.close()
