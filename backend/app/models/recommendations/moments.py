from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class LearningMoment(str, Enum):
    """Types of learning moments."""

    NEW_TOPIC_NO_CONTEXT = "new_topic_no_context"
    NEW_TOPIC_WITH_CONTEXT = "new_topic_with_context"
    CONCEPT_STRUGGLE = "concept_struggle"
    GOAL_DIRECTION = "goal_direction"


class MomentDetection(BaseModel):
    """Result of moment detection analysis."""

    is_moment: bool = Field(description="Whether this is a valuable learning moment")
    moment_type: LearningMoment = Field(description="Type of learning moment detected")
    confidence: float = Field(
        description="Confidence in the detection, between 0 and 1"
    )
    reasoning: str = Field(description="Why this moment was detected")
    signals: List[str] = Field(description="Specific signals that led to detection")
