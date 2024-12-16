from datetime import datetime
from typing import List, Optional, Union

from pydantic import BaseModel, Field


class CompanyMention(BaseModel):
    """Reference to a company in content."""

    name: str
    symbol: Optional[str] = None
    relationship: Optional[str] = None  # e.g., "competitor", "customer", "partner"
    context: str  # The surrounding text that established this relationship


class FinancialMetric(BaseModel):
    """Financial metric with context."""

    name: str  # e.g., "Revenue", "Gross Margin"
    value: Union[float, str]
    period: str  # e.g., "Q2 2024", "FY 2023"
    year_over_year: Optional[float] = None  # % change
    description: Optional[str] = None


class ExtractedSection(BaseModel):
    """A logical section of the content."""

    title: Optional[str] = None
    content: str
    key_points: List[str] = Field(description="Main points from this section")
    companies_discussed: List[CompanyMention] = Field(
        description="Companies mentioned in this section"
    )
    metrics: List[FinancialMetric] = Field(
        description="Financial metrics in this section"
    )


class ContentAnalysisResponse(BaseModel):
    """Complete content analysis from single LLM call."""

    sections: List[ExtractedSection]
    companies: List[CompanyMention]
    metrics: List[FinancialMetric]
    key_topics: List[str] = Field(description="Primary concepts in content")
    summary: str = Field(description="Summary of content")
    sentiment: float = Field(description="Sentiment score from -1 to 1")


class ProcessedContent(BaseModel):
    """Fully processed financial content."""

    content_id: str
    url: str
    title: str
    source: str
    author: Optional[str] = None
    publish_date: datetime
    analysis: ContentAnalysisResponse
    extracted_at: datetime = Field(default_factory=datetime.now)
