import logging
import time
from typing import List

from app.models.recommendations.content import ProcessedContent
from app.models.recommendations.content_filtering import (
    ContentEvaluation,
    ContentValue,
    FilteredContent,
)
from app.models.recommendations.interactions import ContentInteraction
from app.models.recommendations.knowledge_state import KnowledgeState
from app.models.recommendations.moments import LearningMoment
from app.models.recommendations.query_lines import LineAnalysis
from app.prompts import PROMPTS
from app.services.recommendations.cache.openai_cache import OpenAICache
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class ContentFilterer:
    """Filter and rank content based on user context."""

    def __init__(
        self,
        mongodb_uri: str,
        evaluation_model: str = "gpt-4o",
    ):
        self.client = AsyncOpenAI()
        self.model = evaluation_model
        self.cache = OpenAICache(mongodb_uri)

    async def filter_content(
        self,
        candidates: List[ProcessedContent],
        moment: LearningMoment,
        query: str,
        line_analysis: LineAnalysis,
        knowledge_state: KnowledgeState,
        recent_interactions: List[ContentInteraction],
    ) -> FilteredContent:
        """
        Filter content candidates based on user context and knowledge state.

        Uses knowledge state to:
        1. Match content to understanding level
        2. Find content that builds on known concepts
        3. Identify valuable learning progressions
        4. Evaluate explanation style fit
        """
        try:
            valuable_content = []
            attempted_ids = []

            # Evaluate each candidate
            for content in candidates:
                attempted_ids.append(content.content_id)

                # Get content evaluation
                evaluation = await self._evaluate_content(
                    content=content,
                    moment=moment,
                    query=query,
                    line_analysis=line_analysis,
                    knowledge_state=knowledge_state,
                    recent_interactions=recent_interactions,
                )

                if evaluation.is_valuable:
                    logger.info(
                        f"Found valuable content {content.content_id} "
                        f"(score: {evaluation.value_score})"
                    )

                    valuable_content.append(
                        ContentValue(
                            content_id=content.content_id,
                            url=content.url,
                            value_score=evaluation.value_score,
                            explanation=evaluation.explanation,
                            relevant_sections=evaluation.relevant_sections,
                            relevance_context=(
                                "This content aligns with your current understanding "
                                f"of {knowledge_state.current_topic.topic} and "
                                "provides valuable insights about"
                                f"{', '.join(evaluation.relevant_sections)}."
                            ),
                        )
                    )
                else:
                    logger.info(
                        f"Content {content.content_id} not considered valuable. "
                        f"Reason: {evaluation.explanation}"
                    )

            # Sort by value score
            valuable_content.sort(key=lambda x: x.value_score, reverse=True)

            return FilteredContent(
                valuable_content=valuable_content,
                attempted_content=attempted_ids,
            )

        except Exception as e:
            logger.error(f"Error filtering content: {str(e)}")
            raise

    async def _evaluate_content(
        self,
        content: ProcessedContent,
        moment: LearningMoment,
        query: str,
        line_analysis: LineAnalysis,
        knowledge_state: KnowledgeState,
        recent_interactions: List[ContentInteraction],
    ) -> ContentEvaluation:
        """Detailed evaluation of content value."""
        try:
            messages = [
                {
                    "role": "system",
                    "content": PROMPTS["system"]["filter_content"]["evaluate_content"],
                },
                {
                    "role": "user",
                    "content": PROMPTS["user"]["filter_content"][
                        "evaluate_content"
                    ].format(
                        query=query,
                        moment_type=moment.value,
                        goal=line_analysis.inferred_goal,
                        learning_progression=line_analysis.learning_progression,
                        current_focus=line_analysis.current_focus,
                        knowledge_state=self._format_knowledge_state(knowledge_state),
                        title=content.title,
                        summary=content.analysis.summary,
                        sections=self._format_sections(content),
                        topics=", ".join(content.analysis.key_topics),
                        sentiment=content.analysis.sentiment,
                        interactions=self._format_interactions(recent_interactions),
                    ),
                },
            ]

            start_time = time.time()

            # Check cache if available
            if self.cache:
                cached = await self.cache.get_cached_response(
                    messages=messages, model=self.model
                )
                if cached:
                    return ContentEvaluation.model_validate(cached)

            response = await self.client.beta.chat.completions.parse(
                model=self.model,
                temperature=0,
                messages=messages,
                response_format=ContentEvaluation,
            )

            # Store in cache if available
            if self.cache:
                duration_ms = int((time.time() - start_time) * 1000)
                await self.cache.store_call(
                    messages=messages,
                    model=self.model,
                    response=response.choices[0].message.parsed.model_dump(),
                    duration_ms=duration_ms,
                )

            return response.choices[0].message.parsed

        except Exception as e:
            logger.error(f"Error evaluating content: {str(e)}")
            raise

    def _format_knowledge_state(self, knowledge_state: KnowledgeState) -> str:
        """Format knowledge state for content evaluation."""
        lines = [
            f"Current Topic ({knowledge_state.current_topic.topic}):",
            "\nDemonstrated Knowledge:",
        ]

        # Format demonstrated knowledge with evidence
        for concept in knowledge_state.current_topic.concepts:
            if concept.demonstrated_level > 0:
                lines.extend(
                    [
                        f"\n- {concept.concept}:",
                        f"  Understanding Level: {concept.demonstrated_level}",
                        "  Evidence:",
                    ]
                )
                for evidence in concept.demonstration_evidence:
                    lines.append(f"  - {evidence.text}")
                if concept.successful_applications:
                    lines.append("  Successfully Applied In:")
                    for app in concept.successful_applications:
                        lines.append(f"  - {app}")

        # Recently exposed concepts
        lines.extend(
            [
                "\nRecently Exposed To:",
                "(Not yet demonstrated understanding)",
            ]
        )
        for concept in knowledge_state.current_topic.latest_response_concepts:
            lines.append(f"- {concept}")

        # Learning preferences based on demonstrated patterns
        if knowledge_state.current_topic.effective_examples:
            lines.extend(
                [
                    "\nDemonstrated Learning Patterns:",
                    f"- Examples that work: {', '.join(knowledge_state.current_topic.effective_examples)}",  # noqa: E501
                    f"- Progression style: {knowledge_state.current_topic.progression_capability}",  # noqa: E501
                    f"- Connection making: {knowledge_state.current_topic.connection_making}",  # noqa: E501
                    f"- Abstraction level: {knowledge_state.current_topic.abstraction_level}",  # noqa: E501
                ]
            )

        return "\n".join(lines)

    def _format_sections(self, content: ProcessedContent) -> str:
        """Format content sections for evaluation."""
        formatted = []
        for section in content.analysis.sections:
            section_info = [
                f"Section: {section.title}",
                f"Content: {section.content}",
                f"Key Points: {', '.join(section.key_points)}",
            ]

            if section.companies_discussed:
                companies = [
                    f"{c.name} ({c.relationship})" for c in section.companies_discussed
                ]
                section_info.append(f"Companies: {', '.join(companies)}")

            if section.metrics:
                metrics = [
                    f"{m.name}: {m.value} ({m.period})" for m in section.metrics
                ]
                section_info.append(f"Metrics: {', '.join(metrics)}")

            formatted.append("\n".join(section_info))

        return "\n\n".join(formatted)

    def _format_interactions(self, interactions: List[ContentInteraction]) -> str:
        """Format interaction history for evaluation context."""
        if not interactions:
            return "No previous interactions"

        formatted = []
        for interaction in interactions:
            interaction_info = [
                f"- {interaction.interaction_type} with {interaction.content_id}"
            ]
            if interaction.interaction_data:
                if hasattr(interaction.interaction_data, "progress"):
                    interaction_info.append(
                        f"  Progress: {interaction.interaction_data.progress}"
                    )
                if hasattr(interaction.interaction_data, "duration"):
                    interaction_info.append(
                        f"  Duration: {interaction.interaction_data.duration}s"
                    )
            formatted.extend(interaction_info)

        return "\n".join(formatted)
