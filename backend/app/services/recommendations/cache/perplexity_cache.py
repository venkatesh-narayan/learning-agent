import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class PerplexityCallRecord(BaseModel):
    """Record of a Perplexity API call and response."""

    call_id: str  # Hash of messages
    timestamp: datetime
    model: str
    citations: List[str]
    messages: List[Dict[str, str]]
    response: Dict[str, Any]
    duration_ms: int
    error: Optional[str] = None


class PerplexityCache:
    """Cache for Perplexity API calls."""

    def __init__(self, mongodb_uri: str, database: str = "perplexity_cache"):
        self.client = AsyncIOMotorClient(mongodb_uri)
        self.db = self.client[database]

        # Ensure indexes
        self._ensure_indexes()

    def _ensure_indexes(self):
        """Create necessary indexes for efficient querying."""
        # Calls collection
        self.db.calls.create_index("call_id", unique=True)
        self.db.calls.create_index([("timestamp", -1)])
        self.db.calls.create_index([("model", 1), ("timestamp", -1)])
        self.db.calls.create_index("error")

    def _generate_call_id(self, messages: List[Dict], model: str) -> str:
        """Generate unique hash for this API call."""
        # Create hash input
        hash_input = {"messages": messages, "model": model}

        return hashlib.sha256(
            json.dumps(hash_input, sort_keys=True).encode()
        ).hexdigest()

    async def get_cached_response(
        self,
        messages: List[Dict],
        model: str,
    ) -> Optional[Dict]:
        """Get cached response for this exact API call if it exists."""
        try:
            call_id = self._generate_call_id(messages, model)
            record = await self.db.calls.find_one({"call_id": call_id})

            if record:
                logger.info(f"Cache hit for call_id: {call_id}")
                return record["response"]

            logger.info(f"Cache miss for call_id: {call_id}")
            return None

        except Exception as e:
            logger.error(f"Error retrieving from cache: {str(e)}")
            return None

    async def store_call(
        self,
        messages: List[Dict],
        model: str,
        response: Dict,
        citations: List[str],
        duration_ms: int = 0,
        error: Optional[str] = None,
    ) -> None:
        """Store API call result."""
        try:
            call_id = self._generate_call_id(messages, model)

            record = PerplexityCallRecord(
                call_id=call_id,
                timestamp=datetime.now(),
                model=model,
                citations=citations,
                messages=messages,
                response=response,
                duration_ms=duration_ms,
                error=error,
            )

            # Use upsert to handle rare race conditions
            await self.db.calls.update_one(
                {"call_id": call_id},
                {"$set": record.model_dump()},
                upsert=True,
            )

            logger.info(
                f"Stored call {call_id} - "
                f"Duration: {duration_ms}ms, "
                f"Error: {'Yes' if error else 'No'}"
            )

        except Exception as e:
            logger.error(f"Error storing call: {str(e)}")
            raise

    async def clear_all(self):
        """Clear all cached data. Use with caution!"""
        try:
            await self.db.calls.delete_many({})
            logger.info("Cleared all cached Perplexity calls")
        except Exception as e:
            logger.error(f"Error clearing cache: {str(e)}")
            raise
