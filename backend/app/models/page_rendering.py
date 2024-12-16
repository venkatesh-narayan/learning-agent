from enum import Enum

from pydantic import BaseModel


class ProcessStep(str, Enum):
    INITIAL = "initial"  # Getting Perplexity response
    ANALYZING = "analyzing"  # Analyzing query lines
    KNOWLEDGE = "knowledge"  # Analyzing knowledge state
    MOMENT = "moment"  # Detecting learning moment
    STRATEGY = "strategy"  # Generating search strategy
    SEARCHING = "searching"  # Finding content
    EXTRACTING = "extracting"  # Processing found content
    FINALIZING = "finalizing"  # Generating final recommendations
    FAILED = "failed"  # Failed to find useful content. Trying again...


class SelectionRequest(BaseModel):
    user_id: str
    original_query: str
    selected_suggestion: str
