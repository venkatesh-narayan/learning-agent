import asyncio
import logging
import os
from typing import List

import pytest
from app.config import Settings
from app.models.recommendations.content_filtering import ContentValue
from app.models.recommendations.interactions import ContentInteraction, InteractionType
from app.services.recommendations.orchestrator import (
    RecommendationOrchestrator,
    RecommendationResult,
)
from motor.motor_asyncio import AsyncIOMotorClient
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Rich console for pretty output
console = Console()

MOMENT_MESSAGES = {
    "new_topic_no_context": (
        "It looks like this is a new topic that you don't have any background in. "
        "Here are some great supplementary materials to help you get started:"
    ),
    "new_topic_with_context": (
        "You have some relevant background that will help here. "
        "Here are some materials that build on what you already know:"
    ),
    "concept_struggle": (
        "Let's try looking at this from a different angle. "
        "Here are some alternative explanations that might help:"
    ),
    "goal_direction": (
        "Here's a structured approach to help organize your learning in this area:"
    ),
}


class TestHarness:
    """Interactive test harness for recommendation system."""

    def __init__(self):
        settings = Settings()
        self.orchestrator = RecommendationOrchestrator(
            mongodb_uri=settings.mongodb_uri,
            perplexity_api_key=os.getenv("PERPLEXITY_API_KEY"),
            model="gpt-4o",
            max_attempts=3,
        )
        self.db = AsyncIOMotorClient(settings.mongodb_uri).recommendations
        self.test_user = "test_user_1"

    async def setup(self):
        """Clean previous test data."""
        await self.db.queries.delete_many({"user_id": self.test_user})
        await self.db.recommendations.delete_many({"user_id": self.test_user})
        await self.db.interactions.delete_many({"user_id": self.test_user})

    async def run_interactive(self):
        """Run interactive test session."""
        await self.setup()

        console.print(
            "\n🚀 Welcome to the Recommendation System Test Harness!",
            style="bold green",
        )
        console.print(
            "Enter queries as you would in the real system. Type 'exit' to quit.\n"
        )

        while True:
            # Get query
            query = console.input("[bold blue]Enter your query:[/] ")
            if query.lower() == "exit":
                break

            try:
                # First get initial response
                initial = await self.orchestrator.get_initial_response(
                    self.test_user, query
                )

                # Display Perplexity response
                console.print("\n[bold]Perplexity Response:[/]", style="green")
                console.print(initial.perplexity_response)

                # Wait for user to read response
                if console.input("\nPress Enter to see recommendations..."):
                    pass

                # Get recommendations
                result = await self.orchestrator.get_recommendations(initial)

                # Display results
                self._display_recommendations(result)

                # If we got recommendations, simulate interaction
                if result.recommendations:
                    await self._handle_interactions(result.recommendations)

                # Show history
                await self._display_history()

            except Exception as e:
                console.print(f"\n❌ Error: {str(e)}", style="red")
                continue

    def _display_recommendations(self, result: RecommendationResult):
        """Display recommendations."""
        # If we have recommendations
        if result.recommendations:
            # Show moment-specific message
            if result.moment:
                console.print(
                    f"\n{MOMENT_MESSAGES[result.moment.value]}", style="bold yellow"
                )

            rec_table = Table(
                title=f"Found {len(result.recommendations)} Recommendations"
            )
            rec_table.add_column("Score", style="cyan", justify="right")
            rec_table.add_column("URL", style="blue")
            rec_table.add_column("Explanation", style="green")

            for rec in result.recommendations:
                rec_table.add_row(f"{rec.value_score:.2f}", rec.url, rec.explanation)

            console.print(Panel(rec_table, title="Recommendations"))
        else:
            console.print(
                "\n❌ No recommendations generated for this query.", style="yellow"
            )

    async def _handle_interactions(self, recommendations: List[ContentValue]):
        """Simulate user interactions with recommendations."""
        console.print("\n👉 Select a recommendation to interact with (1-N):")

        for i, rec in enumerate(recommendations, 1):
            console.print(f"{i}. {rec.url}")

        try:
            choice = int(console.input("Selection (0 to skip): "))
            if choice == 0:
                return

            if 1 <= choice <= len(recommendations):
                selected = recommendations[choice - 1]

                # Record interaction
                interaction = ContentInteraction(
                    content_id=selected.content_id,
                    content_url=selected.url,
                    interaction_type=InteractionType.read_start,
                    interaction_data={"section": "introduction"},
                    query_context=selected.relevance_context,
                )

                await self.orchestrator.track_interaction(self.test_user, interaction)

                console.print(
                    f"\n✅ Recorded interaction with: {selected.url}", style="green"
                )

        except (ValueError, IndexError):
            console.print("Invalid selection, skipping interaction", style="yellow")

    async def _display_history(self):
        """Show user's interaction history."""
        cursor = (
            self.db.queries.find({"user_id": self.test_user})
            .sort("timestamp", -1)
            .limit(5)
        )

        history = []
        async for doc in cursor:
            history.append(doc)

        if history:
            history_table = Table(title="Recent History (Last 5 Queries)")
            history_table.add_column("Time", style="cyan")
            history_table.add_column("Query", style="green")

            for doc in history:
                history_table.add_row(
                    doc["timestamp"].strftime("%H:%M:%S"), doc["text"]
                )

            console.print(Panel(history_table, title="History"))


@pytest.mark.asyncio
async def test_recommendation_flow():
    """Run interactive test session."""
    harness = TestHarness()
    await harness.run_interactive()


if __name__ == "__main__":
    asyncio.run(test_recommendation_flow())
