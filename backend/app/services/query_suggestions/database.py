import logging
from typing import Any, Dict, List, Optional

import pymongo
from app.models.database import QueryDocument, UserLearningProfileDocument
from app.models.learning import LearningPath, TopicKnowledge, UserLearningProfile
from app.models.query import Query
from motor.motor_asyncio import AsyncIOMotorClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseClient:
    def __init__(self, mongo_uri: str, db_name: str = "query_suggestions"):
        self.client = AsyncIOMotorClient(mongo_uri)
        self.db = self.client[db_name]

    async def init_indexes(self):
        """Initialize database indexes."""

        # Queries collection
        await self.db.queries.create_index(
            [("user_id", pymongo.ASCENDING), ("timestamp", pymongo.DESCENDING)]
        )
        await self.db.queries.create_index(
            [("user_id", pymongo.ASCENDING), ("text", pymongo.ASCENDING)]
        )

        # Learning profiles collection
        await self.db.learning_profiles.create_index("user_id", unique=True)

        # Topics collection
        await self.db.topics.create_index(
            [("user_id", pymongo.ASCENDING), ("topic", pymongo.ASCENDING)]
        )

        # Learning paths collection
        await self.db.learning_paths.create_index(
            [("user_id", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)]
        )

    # Topic group methods
    async def get_topic_groups(self) -> List[Dict[str, Any]]:
        """Get all topic groups."""

        cursor = self.db.topic_groups.find({})
        groups = []
        async for doc in cursor:
            groups.append(doc)

        return groups

    async def store_topic_group(self, group: Dict[str, Any]) -> str:
        """Store a new topic group."""

        try:
            result = await self.db.topic_groups.insert_one(group)
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"Error storing topic group: {str(e)}")
            raise

    async def update_topic_group(self, group: Dict[str, Any]):
        """Update an existing topic group."""

        try:
            await self.db.topic_groups.update_one(
                {"canonical_topic": group["canonical_topic"]},
                {"$set": group},
                upsert=True,
            )
        except Exception as e:
            logger.error(f"Error updating topic group: {str(e)}")
            raise

    # Query methods
    async def store_query(self, user_id: str, query: Query) -> str:
        """Store a new query."""

        doc = QueryDocument(
            user_id=user_id,
            text=query.text,
            timestamp=query.timestamp,
            response_selected=query.response_selected,
        )
        result = await self.db.queries.insert_one(doc.model_dump())
        return str(result.inserted_id)

    async def get_user_queries(self, user_id: str, limit: int = 50) -> List[Query]:
        """Get user's recent queries."""

        cursor = (
            self.db.queries.find({"user_id": user_id})
            .sort("timestamp", -1)
            .limit(limit)
        )

        queries = []
        async for doc in cursor:
            queries.append(
                Query(
                    text=doc["text"],
                    timestamp=doc["timestamp"],
                    response_selected=doc.get("response_selected"),
                )
            )

        return queries

    async def update_query_selection(
        self, user_id: str, original_query: str, selected_suggestion: str
    ):
        """Update which suggestion was selected."""

        await self.db.queries.update_one(
            {"user_id": user_id, "text": original_query},
            {"$set": {"response_selected": selected_suggestion}},
        )

    # Learning profile methods
    async def get_learning_profile(
        self, user_id: str
    ) -> Optional[UserLearningProfile]:
        """Get user's learning profile."""

        doc = await self.db.learning_profiles.find_one({"user_id": user_id})
        if not doc:
            return None

        return UserLearningProfile(
            user_id=doc["user_id"],
            topic_knowledge={
                topic: TopicKnowledge(**knowledge)
                for topic, knowledge in doc["topic_knowledge"].items()
            },
            active_learning_paths=[
                LearningPath(**path) for path in doc["active_learning_paths"]
            ],
            recent_interests=doc["recent_interests"],
        )

    async def update_learning_profile(
        self, user_id: str, profile: UserLearningProfile
    ):
        """Update user's learning profile."""

        # Log the profile state before conversion
        logger.info(
            f"Updating profile for {user_id} - "
            f"paths: {len(profile.active_learning_paths)}, "
            f"topics: {len(profile.topic_knowledge)}"
        )

        doc = UserLearningProfileDocument(
            user_id=profile.user_id,
            topic_knowledge={
                topic: knowledge.model_dump()
                for topic, knowledge in profile.topic_knowledge.items()
            },
            active_learning_paths=[
                path.model_dump() for path in profile.active_learning_paths
            ],
            recent_interests=profile.recent_interests,
        )

        # Log the document state after conversion
        logger.info(
            "Converted to document - "
            f"paths: {len(doc.active_learning_paths)}, "
            f"topics: {len(doc.topic_knowledge)}"
        )

        await self.db.learning_profiles.update_one(
            {"user_id": user_id}, {"$set": doc.model_dump()}, upsert=True
        )

        # Verify the update
        updated_doc = await self.db.learning_profiles.find_one({"user_id": user_id})
        if updated_doc:
            logger.info(
                "Verified update - "
                f"paths: {len(updated_doc['active_learning_paths'])}, "
                f"topics: {len(updated_doc['topic_knowledge'])}"
            )
        else:
            logger.error(f"Failed to verify update for user {user_id}")
