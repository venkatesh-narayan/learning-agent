import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Set

from app.prompts import PROMPTS
from openai import AsyncOpenAI
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class TopicGroup:
    canonical_topic: str
    variations: Set[str]
    last_updated: datetime


class TopicConsolidationService:
    def __init__(self, api_key: str, db_client, model: str):
        self.client = AsyncOpenAI(api_key=api_key)
        self.db = db_client
        self.model = model
        self.topic_groups: Dict[str, TopicGroup] = dict()
        self.initialized = False

    async def initialize(self):
        """Load existing topic groups from database."""
        if not self.initialized:
            self.topic_groups = {}
            stored_groups = await self.db.get_topic_groups()
            logger.info(f"Loading {len(stored_groups)} topic groups from database")

            for group_data in stored_groups:
                try:
                    # Handle both old and new format
                    canonical_topic = group_data.get(
                        "canonical_topic"
                    ) or group_data.get("topic", "")
                    variations = set(group_data.get("variations", []))
                    # Always include canonical topic in variations
                    variations.add(canonical_topic)

                    group = TopicGroup(
                        canonical_topic=canonical_topic,
                        variations=variations,
                        last_updated=group_data.get("last_updated", datetime.now()),
                    )
                    if canonical_topic:  # Only add if we have a valid topic
                        self.topic_groups[canonical_topic] = group
                        logger.debug(
                            f"Loaded topic group: {group.canonical_topic} with "
                            f"{len(group.variations)} variations"
                        )
                except Exception as e:
                    logger.error(f"Error loading topic group: {str(e)}")
                    continue

            self.initialized = True

    async def consolidate_topic(self, new_topic: str) -> str:
        """
        Get canonical topic name for query using existing topics or create new one.
        """

        if not self.initialized:
            await self.initialize()

        logger.debug(f"Consolidating topic for query: {new_topic}")

        # First check if we have this exact topic (case insensitive)
        for canonical, group in self.topic_groups.items():
            if any(v.lower() == new_topic.lower() for v in group.variations):
                return canonical

        # Get all existing topics
        existing_topics = list(self.topic_groups.keys())

        class SelectTopicResponse(BaseModel):
            topic: str
            is_new: bool

        try:
            response = await self.client.beta.chat.completions.parse(
                model=self.model,
                temperature=0,
                messages=[
                    {
                        "role": "system",
                        "content": PROMPTS["system"]["query_suggestions"][
                            "consolidate_topic"
                        ],
                    },
                    {
                        "role": "user",
                        "content": PROMPTS["user"]["query_suggestions"][
                            "consolidate_topic"
                        ].format(
                            query=new_topic,
                            existing_topics=json.dumps(existing_topics, indent=2),
                        ),
                    },
                ],
                response_format=SelectTopicResponse,
            )

            result = response.choices[0].message.parsed
            selected_topic = result.topic.strip()
            is_new = result.is_new

            if is_new:
                # Create new topic group
                group = TopicGroup(
                    canonical_topic=selected_topic,
                    variations={new_topic, selected_topic},  # Include both forms
                    last_updated=datetime.now(),
                )
                self.topic_groups[selected_topic] = group
                await self._store_group(group)
                logger.info(f"Created new topic: {selected_topic}")
            else:
                # Add to existing group
                group = self.topic_groups[selected_topic]
                group.variations.add(new_topic)
                group.last_updated = datetime.now()
                await self._update_group(group)
                logger.info(f"Added to existing topic: {selected_topic}")

            return selected_topic

        except Exception as e:
            logger.error(f"Error consolidating topic: {str(e)}")
            # Fallback to using the topic as is
            logger.warning(f"Using fallback topic: {new_topic}")
            # Create a new group for the fallback
            group = TopicGroup(
                canonical_topic=new_topic,
                variations={new_topic},
                last_updated=datetime.now(),
            )
            self.topic_groups[new_topic] = group
            await self._store_group(group)
            return new_topic

    async def _store_group(self, group: TopicGroup):
        """Store topic group in database."""
        doc = {
            "canonical_topic": group.canonical_topic,
            "variations": list(group.variations),
            "last_updated": group.last_updated,
        }
        try:
            await self.db.store_topic_group(doc)
        except Exception as e:
            logger.error(f"Error storing topic group: {str(e)}")

    async def _update_group(self, group: TopicGroup):
        """Update existing topic group in database."""
        try:
            await self.db.update_topic_group(
                {
                    "canonical_topic": group.canonical_topic,
                    "variations": list(group.variations),
                    "last_updated": group.last_updated,
                }
            )
        except Exception as e:
            logger.error(f"Error updating topic group: {str(e)}")
