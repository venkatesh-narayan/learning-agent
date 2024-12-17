import logging
import os
import traceback
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated

from app.config import get_settings
from app.models.page_rendering import SelectionRequest
from app.models.recommendations.interactions import (
    ContentInteraction,
    InteractionType,
    ReadStartData,
)
from app.services.query_suggestions.database import DatabaseClient
from app.services.query_suggestions.learning import LearningService
from app.services.query_suggestions.llm import LLMService
from app.services.query_suggestions.suggestions import SuggestionsService
from app.services.recommendations.orchestrator import RecommendationOrchestrator
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.websockets import WebSocket

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Store service instances globally
suggestions_service = None
recommendation_orchestrator = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global suggestions_service, recommendation_orchestrator

    # Startup
    settings = get_settings()
    try:
        # Initialize database
        db_client = DatabaseClient(settings.mongodb_uri)
        await db_client.init_indexes()

        # Initialize suggestion services (existing code)
        llm_service = LLMService(os.getenv("OPENAI_API_KEY"), "gpt-4o-mini")
        learning_service = LearningService(llm_service, db_client)
        suggestions_service = SuggestionsService(
            llm_service, db_client, learning_service
        )

        # Initialize recommendation orchestrator (new)
        recommendation_orchestrator = RecommendationOrchestrator(
            mongodb_uri=settings.mongodb_uri,
            perplexity_api_key=os.getenv("PERPLEXITY_API_KEY"),
            model="gpt-4o",
            max_attempts=3,
        )

        # Initialize services
        await suggestions_service.initialize()
        logger.info("Successfully initialized services and database")
    except Exception as e:
        logger.error(f"Failed to initialize: {str(e)}")
        raise
    yield
    # Shutdown cleanup would go here


app = FastAPI(
    title="Learning Agent API",
    description="API for personalized learning recommendations and query suggestions",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Dependencies
async def get_suggestions_service() -> SuggestionsService:
    """Dependency to get configured SuggestionsService."""
    global suggestions_service
    if suggestions_service is None:
        raise RuntimeError("SuggestionsService not initialized")
    return suggestions_service


async def get_recommendation_orchestrator() -> RecommendationOrchestrator:
    """Dependency to get configured RecommendationOrchestrator."""
    global recommendation_orchestrator
    if recommendation_orchestrator is None:
        raise RuntimeError("RecommendationOrchestrator not initialized")
    return recommendation_orchestrator


@app.websocket("/ws/query")
async def websocket_query(
    websocket: WebSocket,
    user_id: str,
    query: str,
    orchestrator: Annotated[
        RecommendationOrchestrator, Depends(get_recommendation_orchestrator)
    ],
    service: Annotated[SuggestionsService, Depends(get_suggestions_service)],
):
    """WebSocket endpoint for query processing with progress updates."""
    await websocket.accept()

    try:
        # Get recommendations with progress updates
        recommendations = await orchestrator.process_with_progress(
            user_id=user_id, query=query, websocket=websocket
        )

        # Tell the frontend that we're getting suggestions
        await websocket.send_json({"step": "suggestions"})

        # Get suggestions after recommendations
        suggestions = await service.get_personalized_suggestions(user_id, query)

        # Send final response
        await websocket.send_json(
            {
                "type": "complete",
                "data": {
                    "recommendations": recommendations,
                    "suggestions": suggestions.model_dump(),
                },
            }
        )

    except Exception as e:
        await websocket.send_json({"type": "error", "message": str(e)})
    finally:
        await websocket.close()


@app.post("/api/selection")
async def record_selection(
    request: SelectionRequest,
    orchestrator: Annotated[
        RecommendationOrchestrator, Depends(get_recommendation_orchestrator)
    ],
):
    """Record selected suggestion or recommendation."""
    try:
        logger.info(f"Recording selection for user {request.user_id}")

        # Create proper ContentInteraction instance
        interaction = ContentInteraction(
            timestamp=datetime.now(),
            content_id=request.selected_suggestion,  # Using URL for now as content ID
            content_url=request.selected_suggestion,
            interaction_type=InteractionType.read_start,
            interaction_data=ReadStartData(
                section="introduction"
            ),  # They're starting to read
            query_context=request.original_query,
            moment_context=None,  # Optional field
        )

        await orchestrator.track_interaction(request.user_id, interaction)
        return {"status": "success"}

    except Exception as e:
        logger.error(f"Error recording selection: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500, detail=f"Error recording selection: {str(e)}"
        )


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
