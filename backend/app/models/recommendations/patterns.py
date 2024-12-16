from typing import Dict, List

from pydantic import BaseModel, Field


class RecommendationPattern(BaseModel):
    """Pattern identified in recommendation generation."""

    pattern_type: str = Field(description="Type of pattern identified")
    identified_patterns: List[str] = Field(description="Specific patterns found")
    effectiveness_metrics: Dict[str, float] = Field(
        description="Metrics measuring effectiveness"
    )
    improvement_suggestions: List[str] = Field(
        description="Ways to improve recommendations"
    )


class SelectionPattern(BaseModel):
    """Pattern identified in user selection behavior."""

    selection_patterns: List[str] = Field(
        description="How users select recommendations"
    )
    learning_signals: Dict[str, str] = Field(
        description="Signals about learning behavior"
    )
    effectiveness_score: float = Field(
        description="How effective selections are, between 0 and 1"
    )
    suggestions: List[str] = Field(description="Ways to improve selection impact")


class LearningImpact(BaseModel):
    """Impact of specific learning interactions."""

    impact_score: float = Field(description="Overall impact score between 0 and 1")
    key_learnings: List[str] = Field(description="Main concepts learned")
    skill_progress: Dict[str, float] = Field(description="Progress in specific skills")
    development_areas: List[str] = Field(description="Areas needing more focus")
