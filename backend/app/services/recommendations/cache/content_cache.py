import logging
from datetime import datetime
from typing import List, Optional

from app.models.recommendations.content import ProcessedContent
from motor.motor_asyncio import AsyncIOMotorClient

logger = logging.getLogger(__name__)


class ContentCache:
    """Cache for processed content."""

    def __init__(self, mongodb_uri: str, database: str = "content_cache"):
        self.client = AsyncIOMotorClient(mongodb_uri)
        self.db = self.client[database]

        # Ensure indexes
        self._ensure_indexes()

    def _ensure_indexes(self):
        """Create necessary indexes for content cache."""
        # URL index for quick lookups
        self.db.processed_content.create_index("url", unique=True)

        # Content ID index
        self.db.processed_content.create_index("content_id", unique=True)

        # Extracted timestamp index for analysis
        self.db.processed_content.create_index("extracted_at")

    async def get_content(
        self, urls: List[str], max_age: Optional[datetime] = None
    ) -> List[ProcessedContent]:
        """Get cached content for URLs."""
        try:
            match = {"url": {"$in": urls}}
            if max_age:
                match["extracted_at"] = {"$gte": max_age}

            cursor = self.db.processed_content.find(match)
            cached = await cursor.to_list(length=None)
            return [ProcessedContent.model_validate(doc) for doc in cached]

        except Exception as e:
            logger.error(f"Error retrieving from cache: {str(e)}")
            return []

    async def store_content(self, content: List[ProcessedContent]):
        """Store processed content in cache."""
        try:
            if not content:
                return

            # Process each item individually instead of bulk write
            for item in content:
                # Convert the entire model to a dictionary first
                content_dict = item.model_dump()

                # Convert datetime objects to strings
                content_dict["extracted_at"] = item.extracted_at.isoformat()
                content_dict["publish_date"] = item.publish_date.isoformat()

                # Convert nested Pydantic models
                content_dict["analysis"] = item.analysis.model_dump()

                # Perform single update
                await self.db.processed_content.update_one(
                    {"url": item.url}, {"$set": content_dict}, upsert=True
                )

            logger.info(f"Cached {len(content)} items successfully")

        except Exception as e:
            logger.error(f"Error caching content: {str(e)}")
            logger.error(f"Content dict: {content_dict}")  # Log the problematic data
            raise

    async def get_by_id(self, content_id: str) -> Optional[ProcessedContent]:
        """Get cached content by ID."""
        try:
            doc = await self.db.processed_content.find_one({"content_id": content_id})
            return ProcessedContent.model_validate(doc) if doc else None

        except Exception as e:
            logger.error(f"Error getting content by ID: {str(e)}")
            return None

    async def clear_all(self):
        """Clear all cached content."""
        try:
            result = await self.db.processed_content.delete_many({})
            logger.info(f"Cleared {result.deleted_count} items from cache")
        except Exception as e:
            logger.error(f"Error clearing cache: {str(e)}")
