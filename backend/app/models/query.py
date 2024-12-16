from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class Query(BaseModel):
    text: str
    timestamp: float
    response_selected: Optional[str] = None


class UserContext(BaseModel):
    recent_queries: List[Query]
    frequent_topics: Dict[str, int]


class QueryAnalysis(BaseModel):
    topic: str = Field(description="The main topic or domain of the query")
    key_aspects: List[str] = Field(
        description="Main aspects or subtopics involved in the query"
    )
    related_interests: List[str] = Field(
        description="Topics the user has shown interest in from their history"
    )


class SuggestionsResponse(BaseModel):
    immediate: List[str] = Field(
        description="Direct follow-up questions related to the current query",
    )
    broader: List[str] = Field(
        description="Questions about related aspects and considerations",
    )
    deeper: List[str] = Field(
        description="Questions that explore underlying concepts and relationships",
    )


class SelectionRequest(BaseModel):
    user_id: str
    original_query: str
    selected_suggestion: str
