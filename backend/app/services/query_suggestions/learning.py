import json
import logging
from typing import List, Optional

from app.models.learning import LearningPath, TopicKnowledge, UserLearningProfile
from app.models.query import QueryAnalysis, SuggestionsResponse
from app.prompts import PROMPTS
from app.services.query_suggestions.database import DatabaseClient
from app.services.query_suggestions.llm import LLMService
from app.services.query_suggestions.topic_consolidation import (
    TopicConsolidationService,
)
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LearningService:
    def __init__(self, llm_service: LLMService, db_client: DatabaseClient):
        self.llm = llm_service
        self.db = db_client
        self.topic_consolidation = TopicConsolidationService(
            api_key=llm_service.client.api_key,
            db_client=db_client,
            model=llm_service.model,
        )

    async def initialize(self):
        """Initialize services."""

        await self.topic_consolidation.initialize()

    async def initialize_learning_profile(self, user_id: str) -> UserLearningProfile:
        """Initialize a new user learning profile."""

        return UserLearningProfile(
            user_id=user_id,
            topic_knowledge=dict(),
            active_learning_paths=[],
            recent_interests=[],
        )

    async def get_or_create_profile(self, user_id: str) -> UserLearningProfile:
        """Get existing profile or create new one."""

        profile = await self.db.get_learning_profile(user_id)
        if not profile:
            profile = await self.initialize_learning_profile(user_id)
            await self.db.update_learning_profile(user_id, profile)
        return profile

    async def _update_learning_path(
        self,
        current_path: LearningPath,
        canonical_topic: str,
        current_query: str,
        known_concepts: List[str],
        relevant_queries: List[str],
    ) -> None:
        """Update a learning path with new information."""

        class UpdateLearningPathResponse(BaseModel):
            knowledge_gaps: List[str]
            next_topics: List[str]

        path_context = {
            "topic": canonical_topic,
            "query": current_query,
            # exclude current query
            "previous_queries": "\n".join(f"- {q}" for q in relevant_queries[:-1]),
            "known_concepts": known_concepts,
            "current_gaps": current_path.knowledge_gaps,
        }

        try:
            response = await self.llm._make_completion(
                [
                    {
                        "role": "system",
                        "content": PROMPTS["system"]["query_suggestions"][
                            "update_learning_path"
                        ],
                    },
                    {
                        "role": "user",
                        "content": PROMPTS["user"]["query_suggestions"][
                            "update_learning_path"
                        ].format(**path_context),
                    },
                ],
                UpdateLearningPathResponse,
            )

            current_path.knowledge_gaps = response.knowledge_gaps
            current_path.next_suggested_topics = response.next_topics
            logger.info(
                f"Updated learning path with {len(current_path.knowledge_gaps)} gaps "
                f"and {len(current_path.next_suggested_topics)} next topics"
            )
        except Exception as e:
            logger.error(f"Error updating learning path: {str(e)}")
            pass

    async def update_profile_with_query(
        self, user_id: str, current_query: str
    ) -> UserLearningProfile:
        """Update user's learning profile based on a new query interaction."""

        profile = await self.get_or_create_profile(user_id)

        # Extract and consolidate topic
        extracted_topic = await self._extract_main_topic(current_query)
        if not extracted_topic:
            logger.info("Couldn't use LLM to extract topic; using heuristics instead")

            # Try to find a potential topic in the query directly
            words = current_query.lower().split()
            for word in words:
                if len(word) > 2 and not word.isspace():  # Basic filtering
                    extracted_topic = word
                    break

            if not extracted_topic:
                logger.warning(f"Could not extract topic from query: {current_query}")
                return profile

        canonical_topic = await self.topic_consolidation.consolidate_topic(
            extracted_topic
        )
        logger.info(
            f"Working with topic: {extracted_topic}, canonical form: {canonical_topic}"
        )

        # Get recent queries only related to this topic
        recent_queries = await self.db.get_user_queries(user_id, limit=20)
        relevant_queries = [
            q.text
            for q in recent_queries
            if await self._is_related_topic(q.text, canonical_topic)
        ]
        relevant_queries.append(current_query)  # Include current query

        logger.info(
            f"Found {len(relevant_queries)} relevant queries for topic "
            f"{canonical_topic}"
        )

        # Get current knowledge state
        current_knowledge = profile.topic_knowledge.get(canonical_topic)

        # Assess topic knowledge with relevant context
        try:
            topic_knowledge_response = await self.llm.assess_topic_knowledge(
                canonical_topic,
                relevant_queries,
                current_knowledge.model_dump() if current_knowledge else None,
            )

            logger.info(
                f"Assessed knowledge for {canonical_topic}: "
                f"{len(topic_knowledge_response.known_concepts)} concepts"
            )

            # Create new TopicKnowledge instance
            topic_knowledge = TopicKnowledge(
                topic=canonical_topic,
                known_concepts=topic_knowledge_response.known_concepts,
            )

            # Update profile's topic knowledge
            profile.topic_knowledge[canonical_topic] = topic_knowledge

        except Exception as e:
            logger.error(f"Error assessing topic knowledge: {str(e)}")
            topic_knowledge = TopicKnowledge(topic=canonical_topic, known_concepts=[])
            profile.topic_knowledge[canonical_topic] = topic_knowledge

        # Update or create learning path for this topic
        current_path = next(
            (p for p in profile.active_learning_paths if canonical_topic in p.topics),
            None,
        )

        if not current_path:
            # Create new learning path
            current_path = LearningPath(
                topics=[canonical_topic],
                current_focus=canonical_topic,
                knowledge_gaps=[],
                next_suggested_topics=[],
            )
            profile.active_learning_paths.append(current_path)

            logger.info(f"Created new learning path for topic: {canonical_topic}")

        # Update the path
        if canonical_topic not in current_path.topics:
            current_path.topics.append(canonical_topic)

        current_path.current_focus = canonical_topic

        # Update path with gaps and next topics
        await self._update_learning_path(
            current_path,
            canonical_topic,
            current_query,
            topic_knowledge.known_concepts,
            relevant_queries,
        )

        # Store updated profile
        await self.db.update_learning_profile(user_id, profile)
        logger.info(
            f"Updated profile - paths: {len(profile.active_learning_paths)}, "
            f"topics: {len(profile.topic_knowledge)}"
        )

        return profile

    async def get_personalized_suggestions(
        self, profile: UserLearningProfile, current_query: str, analysis: QueryAnalysis
    ) -> SuggestionsResponse:
        """Generate suggestions based on learning profile and current context."""

        # Find the current topic's knowledge and active path
        canonical_topic = await self.topic_consolidation.consolidate_topic(
            analysis.topic
        )
        topic_knowledge = profile.topic_knowledge.get(canonical_topic)
        current_path = next(
            (p for p in profile.active_learning_paths if canonical_topic in p.topics),
            None,
        )

        return await self.llm.generate_suggestions(
            query=current_query,
            topic=canonical_topic,
            known_concepts=topic_knowledge.known_concepts if topic_knowledge else [],
            knowledge_gaps=current_path.knowledge_gaps if current_path else [],
            recommended_topics=(
                current_path.next_suggested_topics if current_path else []
            ),
        )

    async def _extract_main_topic(self, query: str) -> Optional[str]:
        """Extract the main topic from a query using LLM."""

        class TopicExtractionResponse(BaseModel):
            topic: str

        messages = [
            {
                "role": "system",
                "content": PROMPTS["system"]["query_suggestions"]["extract_topic"],
            },
            {
                "role": "user",
                "content": PROMPTS["user"]["query_suggestions"][
                    "extract_topic"
                ].format(query=query),
            },
        ]

        try:
            response = await self.llm._make_completion(
                messages, TopicExtractionResponse
            )

            return response.topic
        except Exception as e:
            logger.error(f"Error extracting topic: {str(e)}")
            return None

    async def _is_related_topic(self, query: str, topic: str) -> bool:
        """Use LLM to determine if query is related to topic."""

        class TopicRelationResponse(BaseModel):
            is_related: bool

        messages = [
            {
                "role": "system",
                "content": PROMPTS["system"]["query_suggestions"][
                    "check_topic_relation"
                ],
            },
            {
                "role": "user",
                "content": PROMPTS["user"]["query_suggestions"][
                    "check_topic_relation"
                ].format(query=query, topic=topic),
            },
        ]

        try:
            response = await self.llm._make_completion(messages, TopicRelationResponse)
            return response.is_related
        except Exception:
            return False
