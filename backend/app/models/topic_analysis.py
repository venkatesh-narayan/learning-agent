from typing import List

from pydantic import BaseModel, Field


class Topic(BaseModel):
    """A topic with its key characteristics."""

    name: str = Field(description="Name of the topic")
    category: str = Field(
        description="High-level category (technology, finance, business, etc.)"
    )
    subtopics: List[str] = Field(description="Key subtopics within this topic")
    key_metrics: List[str] = Field(description="Important metrics for this topic")
    related_topics: List[str] = Field(description="Related topic names")


class ThematicAnalysis(BaseModel):
    """Analysis of key themes in content."""

    main_themes: List[str] = Field(description="Primary themes discussed")
    supporting_evidence: List[str] = Field(
        description="Evidence supporting theme identification"
    )
    trend_analysis: str = Field(
        description="Analysis of how themes develop through content"
    )


class TopicAnalysis(BaseModel):
    """Complete topic analysis of content."""

    primary_topic: Topic = Field(description="Main topic of the content")
    secondary_topics: List[Topic] = Field(description="Other topics discussed")
    themes: ThematicAnalysis = Field(description="Thematic analysis")
    content_focus: str = Field(
        description="Assessment of content's topical focus (broad vs specific)"
    )
