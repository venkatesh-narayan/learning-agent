import hashlib
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class OpenAICallRecord(BaseModel):
    """Record of an OpenAI API call and its result."""

    call_id: str  # Hash of messages + model
    timestamp: datetime
    model: str
    messages: List[Dict[str, str]]
    response: Dict[str, Any]  # Raw API response
    processed_result: Optional[Dict] = None  # Any Pydantic models
    duration_ms: int
    error: Optional[str] = None


class OpenAICache:
    """Persistent cache for OpenAI API calls and processed results."""

    def __init__(self, mongodb_uri: str, database: str = "openai_cache"):
        self.client = AsyncIOMotorClient(mongodb_uri)
        self.db = self.client[database]

        # Ensure indexes
        self._ensure_indexes()

    def _ensure_indexes(self):
        """Create necessary indexes for efficient querying."""
        # Completions collection
        self.db.completions.create_index("call_id", unique=True)
        self.db.completions.create_index([("timestamp", -1)])
        self.db.completions.create_index([("model", 1), ("timestamp", -1)])
        self.db.completions.create_index("error")

        # Embeddings collection
        self.db.embeddings.create_index("content_hash", unique=True)
        self.db.embeddings.create_index([("timestamp", -1)])
        self.db.embeddings.create_index([("model", 1), ("timestamp", -1)])

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
        model: str = "gpt-4o",
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
        processed_result: Optional[Dict] = None,
        duration_ms: int = 0,
        error: Optional[str] = None,
    ) -> None:
        """Store API call result and processed data."""
        try:
            call_id = self._generate_call_id(messages, model)

            record = OpenAICallRecord(
                call_id=call_id,
                timestamp=datetime.now(),
                model=model,
                messages=messages,
                response=response,
                processed_result=processed_result,
                duration_ms=duration_ms,
                error=error,
            )

            # Use upsert to handle rare race conditions
            await self.db.calls.update_one(
                {"call_id": call_id}, {"$set": record.model_dump()}, upsert=True
            )

            logger.info(
                f"Stored call {call_id} - "
                f"Duration: {duration_ms}ms, "
                f"Error: {'Yes' if error else 'No'}"
            )

        except Exception as e:
            logger.error(f"Error storing call: {str(e)}")
            raise

    async def get_cached_embedding(
        self, text: str, model: str
    ) -> Optional[List[float]]:
        """Get cached embedding for this text if it exists."""
        try:
            content_hash = hashlib.sha256(text.encode()).hexdigest()
            record = await self.db.embeddings.find_one(
                {"content_hash": content_hash, "model": model}
            )

            if record:
                logger.info(f"Cache hit for embedding hash: {content_hash[:8]}")
                return record["embedding"]

            logger.info(f"Cache miss for embedding hash: {content_hash[:8]}")
            return None

        except Exception as e:
            logger.error(f"Error retrieving embedding from cache: {str(e)}")
            return None

    async def store_embedding(
        self,
        text: str,
        model: str,
        embedding: List[float],
        duration_ms: int = 0,
        error: Optional[str] = None,
    ) -> None:
        """Store embedding result."""
        try:
            content_hash = hashlib.sha256(text.encode()).hexdigest()

            record = {
                "content_hash": content_hash,
                "model": model,
                "text": text,  # Store text for verification/debugging
                "embedding": embedding,
                "timestamp": datetime.now(),
                "duration_ms": duration_ms,
                "error": error,
            }

            # Use upsert to handle rare race conditions
            await self.db.embeddings.update_one(
                {"content_hash": content_hash}, {"$set": record}, upsert=True
            )

            logger.info(
                f"Stored embedding {content_hash[:8]} - "
                f"Duration: {duration_ms}ms, "
                f"Error: {'Yes' if error else 'No'}"
            )

        except Exception as e:
            logger.error(f"Error storing embedding: {str(e)}")
            raise

    async def get_stats(
        self, start_time: Optional[datetime] = None, model: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get usage statistics for analysis."""
        try:
            match = {}
            if start_time:
                match["timestamp"] = {"$gte": start_time}
            if model:
                match["model"] = model

            pipeline = [
                {"$match": match},
                {
                    "$group": {
                        "_id": None,
                        "total_calls": {"$sum": 1},
                        "total_errors": {
                            "$sum": {"$cond": [{"$ne": ["$error", None]}, 1, 0]}
                        },
                        "avg_duration": {"$avg": "$duration_ms"},
                        "max_duration": {"$max": "$duration_ms"},
                        "calls_by_model": {"$push": "$model"},
                    }
                },
            ]

            result = await self.db.calls.aggregate(pipeline).next()

            # Calculate model distribution
            model_counts = {}
            for m in result["calls_by_model"]:
                model_counts[m] = model_counts.get(m, 0) + 1

            return {
                "total_calls": result["total_calls"],
                "error_rate": result["total_errors"] / result["total_calls"],
                "avg_duration_ms": result["avg_duration"],
                "max_duration_ms": result["max_duration"],
                "model_distribution": model_counts,
            }

        except Exception as e:
            logger.error(f"Error getting stats: {str(e)}")
            return {}

    async def clear_all(self) -> None:
        """Clear all cached data. Use with caution!"""
        try:
            await self.db.calls.delete_many({})
            logger.info("Cleared all cached OpenAI calls")
        except Exception as e:
            logger.error(f"Error clearing cache: {str(e)}")
            raise
