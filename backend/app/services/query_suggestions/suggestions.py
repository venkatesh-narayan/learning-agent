import time
from typing import Dict, List

from app.models.query import Query, SuggestionsResponse, UserContext
from app.services.query_suggestions.database import DatabaseClient
from app.services.query_suggestions.learning import LearningService
from app.services.query_suggestions.llm import LLMService


class SuggestionsService:
    def __init__(
        self,
        llm_service: LLMService,
        db_client: DatabaseClient,
        learning_service: LearningService,
    ):
        self.llm = llm_service
        self.db = db_client
        self.learning = learning_service

    async def initialize(self):
        """Initialize all services."""

        await self.learning.initialize()

    async def get_personalized_suggestions(
        self, user_id: str, query: str
    ) -> SuggestionsResponse:
        """Generate personalized suggestions for a user query."""

        # Get user context
        user_queries = await self.db.get_user_queries(user_id)
        user_context = UserContext(
            recent_queries=user_queries,
            frequent_topics=self._analyze_topics(user_queries),
        )

        # Get and update learning profile
        learning_profile = await self.learning.update_profile_with_query(
            user_id, query
        )

        # Analyze query intent and context
        analysis = await self.llm.analyze_query(query, user_context)

        # Generate suggestions using learning profile
        suggestions = await self.learning.get_personalized_suggestions(
            learning_profile, query, analysis
        )

        # Store query for future context
        await self.db.store_query(user_id, Query(text=query, timestamp=time.time()))

        return suggestions

    async def record_selection(
        self, user_id: str, original_query: str, selected_suggestion: str
    ):
        """Record which suggestion was selected and update learning profile."""

        # Update query selection in database
        await self.db.update_query_selection(
            user_id, original_query, selected_suggestion
        )

        # Update profile treating the selection as a new query
        await self.learning.update_profile_with_query(user_id, selected_suggestion)

    def _analyze_topics(self, queries: List[Query]) -> Dict[str, int]:
        """Simple topic frequency analysis from user queries."""

        topics = {}
        for query in queries:
            words = query.text.lower().split()
            for word in words:
                if len(word) > 3:  # Simple filter for potentially meaningful words
                    topics[word] = topics.get(word, 0) + 1
        return topics
