from datetime import datetime
from typing import List

from pydantic import BaseModel, Field


class QueryLine(BaseModel):
    """A sequence of related queries pursuing a specific goal"""

    user_id: str = Field(description="User who made these queries")
    line_id: str = Field(description="Unique UUID for this line")
    queries: List[str] = Field(description="The actual queries in this line")
    timestamps: List[datetime] = Field(description="When each query was made")
    responses: List[str] = Field(description="Perplexity's responses")
    line_topic: str = Field(description="High-level topic this line explores")
    last_updated: datetime = Field(default_factory=datetime.now)


class LineAnalysis(BaseModel):
    """Analysis of a query line's learning progression"""

    inferred_goal: str = Field(description="What user is trying to understand")
    learning_progression: str = Field(description="How understanding is developing")
    current_focus: str = Field(
        description="What they're specifically investigating now"
    )


class LineAnalysisWithTopic(BaseModel):
    """Analysis results including refined topic"""

    analysis: LineAnalysis = Field(description="Analysis of learning progression")
    refined_topic: str = Field(description="Refined topic name for this line")


class QueryLineContext(BaseModel):
    """Analysis of whether a query belongs to an existing line"""

    continues_line: bool = Field(description="Whether this continues an existing line")
    line_index: int = Field(description="Index of continued line if any")
    confidence: float = Field(description="Confidence in this assessment")
    reasoning: str = Field(
        description="Why this query belongs/doesn't belong to a line"
    )
