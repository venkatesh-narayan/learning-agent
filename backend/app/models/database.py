from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel


class QueryDocument(BaseModel):
    user_id: str
    text: str
    timestamp: float
    response_selected: Optional[str] = None


class TopicKnowledgeDocument(BaseModel):
    topic: str
    known_concepts: list[str]


class LearningPathDocument(BaseModel):
    topics: list[str]
    current_focus: str
    knowledge_gaps: list[str]
    next_suggested_topics: list[str]
    created_at: datetime
    updated_at: datetime


class UserLearningProfileDocument(BaseModel):
    user_id: str
    topic_knowledge: Dict[str, Any]  # Stores TopicKnowledgeDocument
    active_learning_paths: list[Any]  # Stores LearningPathDocument
    recent_interests: list[str]
