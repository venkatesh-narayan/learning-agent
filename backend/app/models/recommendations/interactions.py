from datetime import datetime
from enum import Enum
from typing import List, Optional, Union

from pydantic import BaseModel, Field


class HighlightedContent(BaseModel):
    """Content highlighted by user during reading."""

    highlighted_text: str = Field(description="Text that was highlighted")
    surrounding_context: Optional[str] = Field(
        description="Text before/after highlight for context", default=None
    )
    timestamp: datetime = Field(default_factory=datetime.now)


class ReadStartData(BaseModel):
    """Data for when user starts reading content."""

    section: Optional[str] = Field(
        description="Section of content where reading started", default=None
    )


class ReadEndData(BaseModel):
    """Data for when user finishes reading content."""

    read_duration_seconds: int = Field(description="Time spent reading")
    completed: bool = Field(description="Whether they finished the content")


class HighlightData(BaseModel):
    """Data for content highlighting interaction."""

    highlighted_text: str
    surrounding_context: Optional[str] = None
    section: Optional[str] = None


class ReferenceClickData(BaseModel):
    """Data for when user clicks a reference/link."""

    reference_text: str
    reference_url: str
    section: Optional[str] = None


class ProgressUpdateData(BaseModel):
    """Data for reading progress updates."""

    progress: float = Field(ge=0.0, le=1.0)
    current_section: Optional[str] = None


class FollowUpQueryData(BaseModel):
    """Data for follow-up queries after reading."""

    query: str
    related_section: Optional[str] = None


InteractionData = Union[
    ReadStartData,
    ReadEndData,
    HighlightData,
    ReferenceClickData,
    ProgressUpdateData,
    FollowUpQueryData,
]


class InteractionType(str, Enum):
    read_start = "read_start"
    read_end = "read_end"
    highlight = "highlight"
    click_reference = "click_reference"
    progress_update = "progress_update"
    follow_up_query = "follow_up_query"


class ContentInteraction(BaseModel):
    """Raw interaction data with recommended content."""

    timestamp: datetime = Field(default_factory=datetime.now)
    content_id: str = Field(description="Unique identifier for the content")
    content_url: str = Field(description="URL where content was found")
    interaction_type: InteractionType = Field(description="Type of interaction")
    interaction_data: InteractionData
    query_context: Optional[str] = Field(
        description="Query that led to this content", default=None
    )
    moment_context: Optional[str] = Field(
        description="Learning moment type when content was recommended", default=None
    )


class RecommendationContext(BaseModel):
    """Full context of why content was recommended."""

    moment_type: str = Field(description="Type of learning moment detected")
    original_query: str = Field(description="Query that triggered recommendation")
    relevant_history: List[str] = Field(
        description="Previous queries/content that influenced this recommendation"
    )
    matched_aspects: List[str] = Field(
        description="Why this content was considered valuable"
    )


class ContentSelection(BaseModel):
    """Track which recommended content was selected."""

    timestamp: datetime = Field(default_factory=datetime.now)
    user_id: str
    content_id: str
    recommendation_context: RecommendationContext
    explanation_shown: str = Field(
        description="Explanation given for why this content was valuable"
    )


class ContentEngagement(BaseModel):
    """Detailed tracking of how user engaged with content."""

    content_id: str
    read_duration_seconds: Optional[int] = None
    highlights: Optional[List[HighlightedContent]] = None
    clicked_references: Optional[List[str]] = None
    follow_up_queries: Optional[List[str]] = None
    reading_progress: Optional[float] = Field(
        description="Progress through content (0-1)", ge=0.0, le=1.0, default=None
    )
