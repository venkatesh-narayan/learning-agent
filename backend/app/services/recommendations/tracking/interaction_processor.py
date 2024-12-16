import logging
from typing import Dict, List, Optional, Tuple

from app.models.recommendations.interactions import (
    ContentEngagement,
    ContentInteraction,
    ContentSelection,
    HighlightedContent,
)

logger = logging.getLogger(__name__)


class InteractionProcessor:
    """Process and store user interactions with content."""

    def __init__(self, db_client):
        """Initialize with database client."""
        self.db = db_client

        self.interactions_collection = self.db.interactions
        self.engagements_collection = self.db.engagements
        self.selections_collection = self.db.selections

        self._ensure_indexes()

    def _ensure_indexes(self) -> None:
        """Create indexes for better query performance."""
        try:
            # Indexes for interactions collection
            self.interactions_collection.create_index(
                [("user_id", 1), ("timestamp", -1)]
            )
            self.interactions_collection.create_index(
                [("content_id", 1), ("user_id", 1)]
            )

            # Indexes for selections collection
            self.selections_collection.create_index(
                [("user_id", 1), ("timestamp", -1)]
            )

            # Indexes for engagements collection
            self.engagements_collection.create_index(
                [("user_id", 1), ("content_id", 1)], unique=True
            )  # One engagement per user-content pair

            logger.info("Successfully created MongoDB indexes")
        except Exception as e:
            logger.error(f"Error creating indexes: {str(e)}")

    async def track_interaction(
        self, user_id: str, interaction: ContentInteraction
    ) -> None:
        """Store raw interaction data."""
        try:
            await self.interactions_collection.insert_one(
                {
                    "user_id": user_id,
                    **interaction.model_dump(),
                }
            )
        except Exception as e:
            logger.error(f"Error storing interaction: {str(e)}")
            raise

    async def track_selection(self, selection: ContentSelection) -> None:
        """Track content selection with full context."""
        try:
            await self.selections_collection.insert_one(selection.model_dump())
        except Exception as e:
            logger.error(f"Error storing selection: {str(e)}")
            raise

    async def get_content_engagement(
        self,
        user_id: str,
        content_id: str,
    ) -> Optional[ContentEngagement]:
        """Get processed engagement metrics for content."""
        try:
            # Get all interactions for this content
            interactions = await self.interactions_collection.find(
                {"user_id": user_id, "content_id": content_id}
            ).to_list(None)

            if not interactions:
                return None

            # Process interactions into engagement metrics
            engagement = await self._process_engagement_metrics(interactions)

            # Store processed metrics
            await self.engagements_collection.update_one(
                {"user_id": user_id, "content_id": content_id},
                {"$set": engagement.model_dump()},
                upsert=True,
            )

            return engagement

        except Exception as e:
            logger.error(f"Error getting content engagement: {str(e)}")
            raise

    async def get_interactions(
        self, user_id: str, limit: int = 50
    ) -> List[ContentInteraction]:
        """Get user's recent content interactions."""
        try:
            interactions = (
                await self.interactions_collection.find({"user_id": user_id})
                .sort("timestamp", -1)
                .limit(limit)
                .to_list(None)
            )

            return [
                ContentInteraction(
                    timestamp=interaction["timestamp"],
                    content_id=interaction["content_id"],
                    content_url=interaction["content_url"],
                    interaction_type=interaction["interaction_type"],
                    interaction_data=interaction["interaction_data"],
                    query_context=interaction.get("query_context"),
                    moment_context=interaction.get("moment_context"),
                )
                for interaction in interactions
            ]

        except Exception as e:
            logger.error(f"Error getting user interactions: {str(e)}")
            raise

    async def get_selections(
        self, user_id: str, limit: int = 50
    ) -> List[ContentSelection]:
        """Get user's recent content selections."""
        try:
            selections = (
                await self.selections_collection.find({"user_id": user_id})
                .sort("timestamp", -1)
                .limit(limit)
                .to_list(None)
            )

            return [
                ContentSelection(
                    timestamp=selection["timestamp"],
                    user_id=selection["user_id"],
                    content_id=selection["content_id"],
                    recommendation_context=selection["recommendation_context"],
                    explanation_shown=selection["explanation_shown"],
                )
                for selection in selections
            ]

        except Exception as e:
            logger.error(f"Error getting user selections: {str(e)}")
            raise

    async def get_user_history(
        self, user_id: str, limit: int = 50
    ) -> Tuple[List[ContentInteraction], List[ContentSelection]]:
        """Get user's complete interaction history."""
        try:
            interactions = await self.get_interactions(user_id, limit)
            selections = await self.get_selections(user_id, limit)
            return interactions, selections

        except Exception as e:
            logger.error(f"Error getting user history: {str(e)}")
            raise

    async def _process_engagement_metrics(
        self, interactions: List[Dict]
    ) -> ContentEngagement:
        """Process raw interactions into engagement metrics."""
        if not interactions:
            return None

        # Initialize metrics
        engagement = ContentEngagement(content_id=interactions[0]["content_id"])

        # Calculate reading time
        read_end_events = [
            i for i in interactions if i["interaction_type"] == "read_end"
        ]
        if read_end_events:
            # Sum up reading durations from all read_end events
            total_time = sum(
                i["interaction_data"]["read_duration_seconds"] for i in read_end_events
            )
            engagement.read_duration_seconds = total_time

        # Process highlights
        highlights = []
        for i in interactions:
            if i["interaction_type"] == "highlight":
                data = i["interaction_data"]
                highlights.append(
                    HighlightedContent(
                        highlighted_text=data.highlighted_text,
                        surrounding_context=data.surrounding_context,
                        timestamp=i["timestamp"],
                    )
                )
        if highlights:
            engagement.highlights = highlights

        # Track clicked references
        references = [
            f"{i['interaction_data'].reference_text} ({i['interaction_data'].reference_url})"  # noqa: E501
            for i in interactions
            if i["interaction_type"] == "click_reference"
        ]
        if references:
            engagement.clicked_references = references

        # Track follow-up queries
        queries = [
            i["interaction_data"].query
            for i in interactions
            if i["interaction_type"] == "follow_up_query"
        ]
        if queries:
            engagement.follow_up_queries = queries

        # Calculate reading progress
        progress_updates = [
            i for i in interactions if i["interaction_type"] == "progress_update"
        ]
        if progress_updates:
            # Get the maximum progress reached
            engagement.reading_progress = max(
                update["interaction_data"].progress for update in progress_updates
            )

        return engagement
