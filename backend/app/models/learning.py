from typing import Dict, List

from pydantic import BaseModel, Field


class TopicKnowledge(BaseModel):
    topic: str = Field(description="The main topic or subject area")
    known_concepts: List[str] = Field(
        description="List of concepts and topics already understood",
        default_factory=list,
    )


class LearningPath(BaseModel):
    topics: List[str] = Field(description="Sequence of topics in this learning path")
    current_focus: str = Field(description="Currently active topic in this path")
    knowledge_gaps: List[str] = Field(
        description="Identified gaps in understanding that should be addressed",
        default_factory=list,
    )
    next_suggested_topics: List[str] = Field(
        description="Topics recommended to explore next", default_factory=list
    )


class UserLearningProfile(BaseModel):
    user_id: str
    topic_knowledge: Dict[str, TopicKnowledge] = Field(
        default_factory=dict,
        description="Mapping of topics to known concepts",
    )
    active_learning_paths: List[LearningPath] = Field(
        default_factory=list, description="Currently active learning paths"
    )
    recent_interests: List[str] = Field(
        default_factory=list, description="Recently explored topics and interests"
    )
