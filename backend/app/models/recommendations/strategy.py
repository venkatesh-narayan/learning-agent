from typing import List, Optional
from pydantic import BaseModel, Field


class SearchAttempt(BaseModel):
    """Record of a search attempt."""

    query: str = Field(description="Search query used")
    found_valuable_content: bool
    valuable_content_ids: List[str] = Field(default_factory=list)
    failure_reason: Optional[str] = None


class SearchStrategy(BaseModel):
    """Strategy for finding valuable content."""

    search_queries: List[str] = Field(description="Search queries to try")
    technical_depth_target: float = Field(
        description="Target technical sophistication (0-1)"
    )
    required_concepts: List[str] = Field(
        description="Core concepts that content should cover"
    )
    previous_attempts: List[SearchAttempt] = Field(
        default_factory=list,
        description="History of search attempts with this strategy",
    )


class StrategyRefinement(BaseModel):
    """How to refine search strategy based on results."""

    keep_queries: List[str] = Field(description="Queries that should be kept")
    new_queries: List[str] = Field(description="New queries to try")
    adjusted_depth: Optional[float] = Field(
        description="Adjusted technical depth target if needed (0-1)"
    )
    explanation: str = Field(description="Why these refinements were chosen")
