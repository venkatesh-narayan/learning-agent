from typing import List

from pydantic import BaseModel, Field


class LearningHistory(BaseModel):
    """Analyzed learning history relevant to current query."""

    relevant_topics: List[str] = Field(description="Topics related to current query")
    relevant_concepts: List[str] = Field(
        description="Concepts related to current query"
    )
    knowledge_gaps: List[str] = Field(description="Identified gaps in understanding")
    learning_patterns: List[str] = Field(description="Observed learning patterns")
    effective_formats: List[str] = Field(
        description="Content formats that worked well"
    )
