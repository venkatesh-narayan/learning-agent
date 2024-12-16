import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.models.recommendations.content_filtering import ContentValue
from app.models.recommendations.interactions import ContentInteraction
from app.models.recommendations.knowledge_state import KnowledgeState
from app.models.recommendations.moments import LearningMoment
from app.models.recommendations.query_lines import LineAnalysis, QueryLine
from app.services.recommendations.cache.content_cache import ContentCache
from app.services.recommendations.content.content_discovery import ContentDiscovery
from app.services.recommendations.content.content_filterer import ContentFilterer
from app.services.recommendations.knowledge_state.knowledge_analyzer import (
    KnowledgeAnalyzer,
)
from app.services.recommendations.moments.moment_detector import MomentDetector
from app.services.recommendations.perplexity.client import PerplexityClient
from app.services.recommendations.query_lines.grouper import QueryLineGrouper
from app.services.recommendations.query_lines.line_manager import QueryLineManager
from app.services.recommendations.strategy.strategy_generator import StrategyGenerator
from app.services.recommendations.tracking.interaction_processor import (
    InteractionProcessor,
)
from fastapi import WebSocket
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field
from app.models.page_rendering import ProcessStep

logger = logging.getLogger(__name__)


class InitialResponse(BaseModel):
    """Initial response containing Perplexity answer and context."""

    perplexity_response: str
    query_line: QueryLine
    line_analysis: LineAnalysis


class RecommendationResult(BaseModel):
    """Complete result of recommendation process"""

    perplexity_response: str = Field(description="Response from Perplexity")
    moment: Optional[LearningMoment] = Field(
        description="Detected learning moment if any"
    )
    recommendations: Optional[List[ContentValue]] = Field(
        description="Generated recommendations if any"
    )


class RecommendationOrchestrator:
    """Orchestrates the complete recommendation flow."""

    def __init__(
        self,
        mongodb_uri: str,
        perplexity_api_key: str,
        model: str = "gpt-4o-mini",
        max_attempts: int = 3,
    ):
        # Initialize MongoDB
        self.db = AsyncIOMotorClient(mongodb_uri).recommendations

        # Initialize services
        self.perplexity_client = PerplexityClient(perplexity_api_key, mongodb_uri)
        self.content_cache = ContentCache(mongodb_uri)
        self.query_line_manager = QueryLineManager(mongodb_uri, model)
        self.query_line_grouper = QueryLineGrouper(mongodb_uri, model)
        self.knowledge_analyzer = KnowledgeAnalyzer(mongodb_uri, model)
        self.moment_detector = MomentDetector(mongodb_uri, model)
        self.strategy_generator = StrategyGenerator(mongodb_uri, model)
        self.content_discovery = ContentDiscovery(
            mongodb_uri=mongodb_uri,
            openai_engine=model,
            perplexity_api_key=perplexity_api_key,
            cache=self.content_cache,
        )
        self.content_filter = ContentFilterer(mongodb_uri, model)
        self.interaction_processor = InteractionProcessor(self.db)

        # Configuration
        self.max_attempts = max_attempts

    async def get_initial_response(self, user_id: str, query: str) -> InitialResponse:
        """Get initial Perplexity response and process query line."""
        try:
            # First determine query line
            query_line, line_analysis = (
                await self.query_line_manager.get_or_update_line(
                    user_id=user_id, query=query
                )
            )
            logger.info(f"Processed query into line: {query_line.line_topic}")
            logger.info(f"Line analysis: {line_analysis}")

            # Get Perplexity response and update line
            perplexity_response, _, updated_line = (
                await self.perplexity_client.get_response(
                    query=query, query_line=query_line
                )
            )

            # Update line with response
            await self.query_line_manager._update_line(updated_line)

            return InitialResponse(
                perplexity_response=perplexity_response,
                query_line=updated_line,
                line_analysis=line_analysis,
            )

        except Exception as e:
            logger.error(f"Error getting initial response: {str(e)}")
            raise

    async def get_recommendations(
        self, initial_response: InitialResponse
    ) -> RecommendationResult:
        """Generate content recommendations based on initial response."""
        try:
            # Get all query lines and find related ones
            all_lines = await self.query_line_manager._get_user_lines(
                initial_response.query_line.user_id, limit=100
            )
            related_lines = await self.query_line_grouper.get_related_lines(
                current_line=initial_response.query_line, all_lines=all_lines
            )
            logger.info(f"Found {len(related_lines)} related query lines")

            # Analyze knowledge state across related lines
            knowledge_state = await self.knowledge_analyzer.analyze_knowledge(
                current_line=initial_response.query_line,
                related_lines=related_lines,
            )
            logger.info("Analyzed knowledge state")

            # Get user's interaction history
            recent_interactions = await self.interaction_processor.get_interactions(
                user_id=initial_response.query_line.user_id, limit=100
            )

            # Detect learning moment using knowledge state
            moment = await self.moment_detector.detect_moment(
                query=initial_response.query_line.queries[-1],
                line_analysis=initial_response.line_analysis,
                knowledge_state=knowledge_state,
                recent_interactions=recent_interactions,
            )

            if not moment:
                logger.info(
                    "No learning moment detected for query: "
                    f"{initial_response.query_line.queries[-1]}"
                )
                return RecommendationResult(
                    perplexity_response=initial_response.perplexity_response,
                    moment=None,
                    recommendations=None,
                )

            # Generate initial strategy using knowledge state
            strategy = await self.strategy_generator.generate_strategy(
                query=initial_response.query_line.queries[-1],
                moment=moment,
                line_analysis=initial_response.line_analysis,
                knowledge_state=knowledge_state,
                recent_interactions=recent_interactions,
            )

            attempt = 0
            while strategy and attempt < self.max_attempts:
                logger.info(
                    f"Attempt {attempt + 1} for query: "
                    f"{initial_response.query_line.queries[-1]}"
                )

                # Find content
                content = await self.content_discovery.execute_search(strategy)

                # Filter content using knowledge state
                logger.info(f"Filtering {len(content)} candidates")
                filtered = await self.content_filter.filter_content(
                    candidates=content,
                    moment=moment,
                    query=initial_response.query_line.queries[-1],
                    line_analysis=initial_response.line_analysis,
                    knowledge_state=knowledge_state,
                    recent_interactions=recent_interactions,
                )

                # If we found valuable content, store and return it
                if filtered.valuable_content:
                    await self._store_recommendations(
                        user_id=initial_response.query_line.user_id,
                        query=initial_response.query_line.queries[-1],
                        recommendations=filtered.valuable_content,
                        moment=moment,
                        line_analysis=initial_response.line_analysis,
                        knowledge_state=knowledge_state,
                    )
                    return RecommendationResult(
                        perplexity_response=initial_response.perplexity_response,
                        moment=moment,
                        recommendations=filtered.valuable_content,
                    )

                # Record failed attempt and refine strategy if needed
                strategy = await self.strategy_generator.record_attempt(
                    strategy=strategy,
                    query=initial_response.query_line.queries[-1],
                    valuable_content_ids=[],
                    failure_reason="No valuable content found",
                )

                # Generate refined strategy using knowledge state
                strategy = await self.strategy_generator.generate_strategy(
                    query=initial_response.query_line.queries[-1],
                    moment=moment,
                    line_analysis=initial_response.line_analysis,
                    knowledge_state=knowledge_state,
                    recent_interactions=recent_interactions,
                    previous_strategy=strategy,
                )

                attempt += 1

            logger.info(f"Failed to find valuable content after {attempt} attempts")
            return RecommendationResult(
                perplexity_response=initial_response.perplexity_response,
                moment=moment,
                recommendations=None,
            )

        except Exception as e:
            logger.error(f"Error getting recommendations: {str(e)}")
            raise

    async def process_with_progress(
        self, user_id: str, query: str, websocket: WebSocket
    ) -> Dict[str, Any]:
        """Process query and send progress updates via WebSocket."""
        try:
            # Getting initial response
            await websocket.send_json({"step": ProcessStep.INITIAL})
            initial_response = await self.get_initial_response(user_id, query)

            # Analyzing lines
            await websocket.send_json({"step": ProcessStep.ANALYZING})
            all_lines = await self.query_line_manager._get_user_lines(
                user_id, limit=100
            )
            related_lines = await self.query_line_grouper.get_related_lines(
                current_line=initial_response.query_line, all_lines=all_lines
            )

            # Analyzing knowledge state
            await websocket.send_json({"step": ProcessStep.KNOWLEDGE})
            knowledge_state = await self.knowledge_analyzer.analyze_knowledge(
                current_line=initial_response.query_line,
                related_lines=related_lines,
            )

            recent_interactions = await self.interaction_processor.get_interactions(
                user_id=initial_response.query_line.user_id, limit=100
            )

            # Detecting moment
            await websocket.send_json({"step": ProcessStep.MOMENT})
            moment = await self.moment_detector.detect_moment(
                query=initial_response.query_line.queries[-1],
                line_analysis=initial_response.line_analysis,
                knowledge_state=knowledge_state,
                recent_interactions=recent_interactions,
            )

            recommendations = []
            if moment:
                # Generate search strategy
                await websocket.send_json({"step": ProcessStep.STRATEGY})
                strategy = await self.strategy_generator.generate_strategy(
                    query=initial_response.query_line.queries[-1],
                    moment=moment,
                    line_analysis=initial_response.line_analysis,
                    knowledge_state=knowledge_state,
                    recent_interactions=recent_interactions,
                )

                attempt = 0
                while strategy and attempt < self.max_attempts:
                    # Search for content
                    await websocket.send_json({"step": ProcessStep.SEARCHING})
                    content = await self.content_discovery.execute_search(strategy)

                    # Process content
                    await websocket.send_json({"step": ProcessStep.EXTRACTING})
                    filtered = await self.content_filter.filter_content(
                        candidates=content,
                        moment=moment,
                        query=initial_response.query_line.queries[-1],
                        line_analysis=initial_response.line_analysis,
                        knowledge_state=knowledge_state,
                        recent_interactions=recent_interactions,
                    )

                    # Finalize
                    await websocket.send_json({"step": ProcessStep.FINALIZING})
                    # If we found valuable content, store and return it
                    if filtered.valuable_content:
                        await self._store_recommendations(
                            user_id=initial_response.query_line.user_id,
                            query=initial_response.query_line.queries[-1],
                            recommendations=filtered.valuable_content,
                            moment=moment,
                            line_analysis=initial_response.line_analysis,
                            knowledge_state=knowledge_state,
                        )

                        recommendations = filtered.valuable_content
                        break

                    else:
                        await websocket.send_json({"step": ProcessStep.FAILED})

                        # Record failed attempt and refine strategy if needed
                        strategy = await self.strategy_generator.record_attempt(
                            strategy=strategy,
                            query=initial_response.query_line.queries[-1],
                            valuable_content_ids=[],
                            failure_reason="No valuable content found",
                        )

                        # Generate refined strategy using knowledge state
                        await websocket.send_json({"step": ProcessStep.STRATEGY})
                        strategy = await self.strategy_generator.generate_strategy(
                            query=initial_response.query_line.queries[-1],
                            moment=moment,
                            line_analysis=initial_response.line_analysis,
                            knowledge_state=knowledge_state,
                            recent_interactions=recent_interactions,
                            previous_strategy=strategy,
                        )

                        attempt += 1

                if not recommendations:
                    await websocket.send_json({"step": ProcessStep.FAILED})

            return {
                "perplexity_response": initial_response.perplexity_response,
                "moment": moment.value,
                "recommendations": [rec.model_dump() for rec in recommendations],
                "line_analysis": initial_response.line_analysis.model_dump(),
            }

        except Exception as e:
            logger.error(f"Error in recommendation process: {str(e)}")
            raise

    async def _store_recommendations(
        self,
        user_id: str,
        query: str,
        recommendations: List[ContentValue],
        moment: LearningMoment,
        line_analysis: LineAnalysis,
        knowledge_state: KnowledgeState,
    ):
        """Store recommendations for analysis."""
        try:
            doc = {
                "user_id": user_id,
                "query": query,
                "moment": moment.value,
                "line_analysis": line_analysis.model_dump(),
                "knowledge_state": knowledge_state.model_dump(),
                "recommendations": [r.model_dump() for r in recommendations],
                "timestamp": datetime.now(),
            }
            await self.db.recommendations.insert_one(doc)
        except Exception as e:
            logger.error(f"Error storing recommendations: {str(e)}")

    async def track_interaction(self, user_id: str, interaction: ContentInteraction):
        """Track user interaction with recommended content."""
        try:
            await self.interaction_processor.track_interaction(
                user_id=user_id, interaction=interaction
            )
        except Exception as e:
            logger.error(f"Error tracking interaction: {str(e)}")
