from typing import List

from pydantic import BaseModel, Field


class ContentValue(BaseModel):
    """Evaluation of content value for user's current context."""

    content_id: str
    url: str
    value_score: float = Field(description="Overall value score (0-1)")
    explanation: str = Field(
        description="Clear explanation of why this content is valuable"
    )
    relevant_sections: List[str] = Field(description="IDs of most relevant sections")
    relevance_context: str = Field(
        description="Brief context of how content relates to user's needs"
    )


class ContentEvaluation(BaseModel):
    """LLM evaluation of content value."""

    is_valuable: bool = Field(description="Whether content provides genuine value")
    explanation: str = Field(description="Why content is/isn't valuable")
    relevant_sections: List[str] = Field(description="Section IDs that provide value")
    value_score: float = Field(description="Value score if valuable (0-1)")


class FilteredContent(BaseModel):
    """Results of content filtering."""

    valuable_content: List[ContentValue]
    attempted_content: List[str] = Field(description="Content IDs that were evaluated")
