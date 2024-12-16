import logging
import time
from typing import List, Optional

from app.models.recommendations.interactions import ContentInteraction
from app.models.recommendations.knowledge_state import KnowledgeState
from app.models.recommendations.moments import LearningMoment
from app.models.recommendations.query_lines import LineAnalysis
from app.models.recommendations.strategy import (
    SearchAttempt,
    SearchStrategy,
    StrategyRefinement,
)
from app.prompts import PROMPTS
from app.services.recommendations.cache.openai_cache import OpenAICache
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class StrategyGenerator:
    """Generate and refine search strategies for finding valuable content."""

    def __init__(self, mongodb_uri: str, model: str = "gpt-4o"):
        self.client = AsyncOpenAI()
        self.model = model
        self.cache = OpenAICache(mongodb_uri)

    async def generate_strategy(
        self,
        query: str,
        moment: LearningMoment,
        line_analysis: LineAnalysis,
        knowledge_state: KnowledgeState,
        recent_interactions: List[ContentInteraction],
        previous_strategy: Optional[SearchStrategy] = None,
    ) -> SearchStrategy:
        """Generate search strategy based on user context and knowledge state."""
        try:
            # If we have a previous strategy, analyze its effectiveness
            if previous_strategy and previous_strategy.previous_attempts:
                refinement = await self._analyze_previous_attempts(
                    previous_strategy=previous_strategy,
                    query=query,
                    moment=moment,
                    knowledge_state=knowledge_state,
                )

                return SearchStrategy(
                    search_queries=[*refinement.keep_queries, *refinement.new_queries],
                    technical_depth_target=(
                        refinement.adjusted_depth
                        if refinement.adjusted_depth is not None
                        else previous_strategy.technical_depth_target
                    ),
                    required_concepts=previous_strategy.required_concepts,
                    previous_attempts=previous_strategy.previous_attempts,
                )

            # Generate new strategy
            messages = [
                {
                    "role": "system",
                    "content": PROMPTS["system"]["strategy"]["generate_strategy"],
                },
                {
                    "role": "user",
                    "content": PROMPTS["user"]["strategy"]["generate_strategy"].format(
                        query=query,
                        moment_type=moment.value,
                        goal=line_analysis.inferred_goal,
                        progression=line_analysis.learning_progression,
                        current_focus=line_analysis.current_focus,
                        current_knowledge=self._format_current_knowledge(
                            knowledge_state
                        ),
                        learning_patterns=self._format_learning_patterns(
                            knowledge_state
                        ),
                        interactions=self._format_interactions(recent_interactions),
                    ),
                },
            ]

            start_time = time.time()

            # Check cache
            cached = await self.cache.get_cached_response(
                messages=messages, model=self.model
            )
            if cached:
                logger.info("Using cached strategy")
                return SearchStrategy.model_validate(cached)

            logger.info("Generating new strategy...")
            response = await self.client.beta.chat.completions.parse(
                model=self.model,
                temperature=0,
                messages=messages,
                response_format=SearchStrategy,
            )

            result = response.choices[0].message.parsed

            # Store in cache
            duration_ms = int((time.time() - start_time) * 1000)
            await self.cache.store_call(
                messages=messages,
                model=self.model,
                response=result.model_dump(),
                duration_ms=duration_ms,
            )

            return result

        except Exception as e:
            logger.error(f"Error generating strategy: {str(e)}")
            raise

    def _format_current_knowledge(self, knowledge_state: KnowledgeState) -> str:
        """Format current knowledge state for strategy generation."""
        lines = [
            f"Current Topic ({knowledge_state.current_topic.topic}):",
            "Demonstrated Understanding:",
        ]

        for concept in knowledge_state.current_topic.concepts:
            if concept.demonstrated_level > 0:
                lines.extend(
                    [
                        f"- {concept.concept}:",
                        f"  Level: {concept.demonstrated_level}",
                        "  Evidence:",
                    ]
                )
                for evidence in concept.demonstration_evidence:
                    lines.append(f"  - {evidence.text}")
                if concept.successful_applications:
                    lines.append("  Successfully Applied In:")
                    for app in concept.successful_applications:
                        lines.append(f"  - {app}")

        lines.extend(
            [
                "\nExposed To (Not Yet Demonstrated):",
                *[
                    f"- {concept}"
                    for concept in knowledge_state.current_topic.latest_response_concepts  # noqa: E501
                ],
            ]
        )

        if knowledge_state.current_topic.effective_examples:
            lines.extend(
                [
                    "\nLearning Style:",
                    f"- Effective Examples: {', '.join(knowledge_state.current_topic.effective_examples)}",  # noqa: E501
                    f"- Progression: {knowledge_state.current_topic.progression_capability}",  # noqa: E501
                    f"- Abstraction: {knowledge_state.current_topic.abstraction_level}",  # noqa: E501
                ]
            )

        return "\n".join(lines)

    def _format_learning_patterns(self, knowledge_state: KnowledgeState) -> str:
        """Format learning patterns for strategy generation."""
        if not knowledge_state.overall_patterns:
            return "Learning patterns not yet established"

        return "Learning Patterns:\n" + "\n".join(
            f"- {pattern}" for pattern in knowledge_state.overall_patterns
        )

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

    async def record_attempt(
        self,
        strategy: SearchStrategy,
        query: str,
        valuable_content_ids: List[str],
        failure_reason: Optional[str] = None,
    ) -> SearchStrategy:
        """Record results of a search attempt."""
        attempt = SearchAttempt(
            query=query,
            found_valuable_content=bool(valuable_content_ids),
            valuable_content_ids=valuable_content_ids,
            failure_reason=failure_reason,
        )

        return SearchStrategy(
            search_queries=strategy.search_queries,
            technical_depth_target=strategy.technical_depth_target,
            required_concepts=strategy.required_concepts,
            previous_attempts=[*strategy.previous_attempts, attempt],
        )

    async def _analyze_previous_attempts(
        self,
        previous_strategy: SearchStrategy,
        query: str,
        moment: LearningMoment,
        knowledge_state: KnowledgeState,
    ) -> StrategyRefinement:
        """Analyze previous attempts to refine strategy."""
        try:
            messages = [
                {
                    "role": "system",
                    "content": PROMPTS["system"]["search"]["analyze_strategy"],
                },
                {
                    "role": "user",
                    "content": PROMPTS["user"]["search"]["analyze_strategy"].format(
                        query=query,
                        moment_type=moment.value,
                        knowledge_state=self._format_current_knowledge(
                            knowledge_state
                        ),
                        learning_patterns=self._format_learning_patterns(
                            knowledge_state
                        ),
                        technical_depth=previous_strategy.technical_depth_target,
                        concepts=previous_strategy.required_concepts,
                        attempts=self._format_attempts(
                            previous_strategy.previous_attempts
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
                return StrategyRefinement.model_validate(cached)

            response = await self.client.beta.chat.completions.parse(
                model=self.model,
                messages=messages,
                temperature=0,
                response_format=StrategyRefinement,
            )

            result = response.choices[0].message.parsed

            # Store in cache
            duration_ms = int((time.time() - start_time) * 1000)
            await self.cache.store_call(
                messages=messages,
                model=self.model,
                response=result.model_dump(),
                duration_ms=duration_ms,
            )

            return result

        except Exception as e:
            logger.error(f"Error analyzing previous attempts: {str(e)}")
            # Conservative fallback: keep successful queries, add original
            successful_queries = [
                attempt.query
                for attempt in previous_strategy.previous_attempts
                if attempt.found_valuable_content
            ]
            return StrategyRefinement(
                keep_queries=successful_queries,
                new_queries=[query] if query not in successful_queries else [],
                adjusted_depth=None,
                explanation="Error during analysis, keeping successful queries",
            )

    def _format_attempts(self, attempts: List[SearchAttempt]) -> str:
        """Format search attempts for analysis."""
        if not attempts:
            return "No previous attempts"

        formatted = []
        for i, attempt in enumerate(attempts, 1):
            formatted.extend(
                [
                    f"\nAttempt {i}:",
                    f"Query: {attempt.query}",
                    "Result: "
                    + (
                        f"Found content: {', '.join(attempt.valuable_content_ids)}"
                        if attempt.found_valuable_content
                        else f"Failed: {attempt.failure_reason or 'No reason given'}"
                    ),
                ]
            )

        return "\n".join(formatted)
