from typing import List
from pydantic import BaseModel, Field


class ConceptEvidence(BaseModel):
    """Evidence of concept understanding or exposure"""

    source: str = Field(description="Source of evidence (e.g., 'query', 'response')")
    text: str = Field(description="The actual text showing evidence")


class ConceptUnderstanding(BaseModel):
    """Understanding of a specific concept"""

    concept: str = Field(description="The specific concept")
    demonstrated_level: float = Field(
        description="Level of demonstrated understanding (0-1)"
    )
    demonstration_evidence: List[ConceptEvidence] = Field(
        description="Evidence of demonstrated understanding", default_factory=list
    )
    exposed_through: List[ConceptEvidence] = Field(
        description="When and how they were exposed to this concept",
        default_factory=list,
    )
    successful_applications: List[str] = Field(
        description="Examples of successful concept application", default_factory=list
    )
    misconceptions: List[str] = Field(
        description="Identified misconceptions or struggles", default_factory=list
    )


class TopicKnowledge(BaseModel):
    """Knowledge state within a specific topic"""

    topic: str = Field(description="Topic being learned")
    concepts: List[ConceptUnderstanding] = Field(
        description="Understanding of specific concepts"
    )
    explanation_preferences: List[str] = Field(
        description="Learning approaches that work well", default_factory=list
    )
    progression_capability: str = Field(description="How they build understanding")
    connection_making: str = Field(description="How well they connect concepts")
    abstraction_level: str = Field(description="Preferred level of abstraction")
    effective_examples: List[str] = Field(
        description="Types of examples that resonated", default_factory=list
    )
    latest_response_concepts: List[str] = Field(
        description="Concepts introduced in latest response", default_factory=list
    )


class KnowledgeState(BaseModel):
    """Complete learning and knowledge state"""

    current_topic: TopicKnowledge = Field(description="Knowledge in current topic")
    related_topics: List[TopicKnowledge] = Field(
        description="Knowledge in related areas"
    )
    overall_patterns: List[str] = Field(description="Learning patterns across topics")
