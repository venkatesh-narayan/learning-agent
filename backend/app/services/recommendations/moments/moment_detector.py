import logging
import time
from typing import List, Optional

from app.models.recommendations.interactions import ContentInteraction
from app.models.recommendations.knowledge_state import KnowledgeState, TopicKnowledge
from app.models.recommendations.moments import LearningMoment, MomentDetection
from app.models.recommendations.query_lines import LineAnalysis
from app.prompts import PROMPTS
from app.services.recommendations.cache.openai_cache import OpenAICache
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class MomentDetector:
    """Detects valuable moments for providing learning recommendations."""

    def __init__(self, mongodb_uri: str, model: str = "gpt-4o"):
        self.client = AsyncOpenAI()
        self.model = model
        self.cache = OpenAICache(mongodb_uri)

    async def detect_moment(
        self,
        query: str,
        line_analysis: LineAnalysis,
        knowledge_state: KnowledgeState,
        recent_interactions: List[ContentInteraction],
    ) -> Optional[LearningMoment]:
        """Detect if this is a valuable moment for recommendations."""
        try:
            messages = [
                {
                    "role": "system",
                    "content": PROMPTS["system"]["moments"]["moment_detection"],
                },
                {
                    "role": "user",
                    "content": PROMPTS["user"]["moments"]["moment_detection"].format(
                        query=query,
                        goal=line_analysis.inferred_goal,
                        learning_progression=line_analysis.learning_progression,
                        current_focus=line_analysis.current_focus,
                        current_topic_knowledge=self._format_topic_knowledge(
                            knowledge_state.current_topic
                        ),
                        related_knowledge=self._format_related_knowledge(
                            knowledge_state.related_topics
                        ),
                        learning_patterns=self._format_learning_patterns(
                            knowledge_state.overall_patterns
                        ),
                        interaction_history=self._format_interactions(
                            recent_interactions
                        ),
                    ),
                },
            ]

            start_time = time.time()

            # Check cache
            cached = await self.cache.get_cached_response(
                messages=messages, model=self.model
            )
            if cached:
                detection = MomentDetection.model_validate(cached)
            else:
                response = await self.client.beta.chat.completions.parse(
                    model=self.model,
                    temperature=0,
                    messages=messages,
                    response_format=MomentDetection,
                )
                detection = response.choices[0].message.parsed

                # Store in cache
                duration_ms = int((time.time() - start_time) * 1000)
                await self.cache.store_call(
                    messages=messages,
                    model=self.model,
                    response=detection.model_dump(),
                    duration_ms=duration_ms,
                )

            if detection.is_moment:
                logger.info(
                    f"Detected {detection.moment_type} moment. "
                    f"Confidence: {detection.confidence}. "
                    f"Reasoning: {detection.reasoning}"
                )
                return detection.moment_type

            logger.info(f"No learning moment detected for query '{query}'")
            return None

        except Exception as e:
            logger.error(f"Error detecting moment: {str(e)}")
            raise

    def _format_topic_knowledge(self, topic: TopicKnowledge) -> str:
        """Format current topic knowledge state emphasizing demonstrated knowledge."""
        lines = [
            f"Topic: {topic.topic}",
            "\nDemonstrated Knowledge:",
        ]

        for concept in topic.concepts:
            if concept.demonstrated_level > 0:
                lines.extend(
                    [
                        f"\nConcept: {concept.concept}",
                        f"Understanding Level: {concept.demonstrated_level}",
                        "Evidence:",
                    ]
                )
                for evidence in concept.demonstration_evidence:
                    lines.append(f"- {evidence.text} ({evidence.source})")
                if concept.successful_applications:
                    lines.append("Successfully Applied In:")
                    for app in concept.successful_applications:
                        lines.append(f"- {app}")

        lines.extend(
            ["\nRecently Exposed Concepts:", "(Not yet demonstrated understanding)"]
        )
        for concept in topic.latest_response_concepts:
            lines.append(f"- {concept}")

        if topic.effective_examples:
            lines.extend(
                [
                    "\nEffective Learning Patterns:",
                    f"- Examples that work: {', '.join(topic.effective_examples)}",
                    f"- Progression style: {topic.progression_capability}",
                    f"- Connection making: {topic.connection_making}",
                    f"- Abstraction level: {topic.abstraction_level}",
                ]
            )

        return "\n".join(lines)

    def _format_related_knowledge(self, topics: List[TopicKnowledge]) -> str:
        """Format related topics knowledge, focusing on demonstrated understanding."""
        if not topics:
            return "No related topic knowledge"

        lines = ["Related Knowledge:"]
        for topic in topics:
            demonstrated_concepts = [
                c for c in topic.concepts if c.demonstrated_level > 0
            ]
            if demonstrated_concepts:
                lines.extend([f"\nTopic: {topic.topic}", "Demonstrated Concepts:"])
                for concept in demonstrated_concepts:
                    lines.append(
                        f"- {concept.concept} "
                        f"(Understanding: {concept.demonstrated_level})"
                    )

        return "\n".join(lines)

    def _format_learning_patterns(self, patterns: List[str]) -> str:
        """Format overall learning patterns."""
        if not patterns:
            return "No established learning patterns"
        return "Learning Patterns:\n" + "\n".join(f"- {p}" for p in patterns)

    def _format_interactions(self, interactions: List[ContentInteraction]) -> str:
        """Format interaction history."""
        if not interactions:
            return "No previous interactions"

        formatted = []
        for interaction in interactions:
            formatted.append(
                f"- {interaction.interaction_type} with {interaction.content_id}"
            )
            if interaction.interaction_data:
                if hasattr(interaction.interaction_data, "progress"):
                    formatted.append(
                        f"  Progress: {interaction.interaction_data.progress}"
                    )

        return "\n".join(formatted)
