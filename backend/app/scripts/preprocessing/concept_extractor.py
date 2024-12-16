from typing import Optional

from app.models.recommendations.content_analysis import ContentAnalysis
from app.prompts import PROMPTS
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential


class ConceptExtractor:
    """Extract structured concepts from financial content using LLM."""

    def __init__(self, model: str = "gpt-4o-mini"):
        self.client = AsyncOpenAI()
        self.model = model

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True,
    )
    async def extract_concepts(self, text: str) -> Optional[ContentAnalysis]:
        """Extract concepts and relationships from text."""
        try:
            response = await self.client.beta.chat.completions.parse(
                model=self.model,
                temperature=0,
                messages=[
                    {
                        "role": "system",
                        "content": PROMPTS["system"]["content_preprocessing"][
                            "concept_extraction"
                        ],
                    },
                    {
                        "role": "user",
                        "content": PROMPTS["user"]["content_preprocessing"][
                            "concept_extraction"
                        ].format(text=text),
                    },
                ],
                response_format=ContentAnalysis,
            )

            return response.choices[0].message.parsed

        except Exception as e:
            # Log error and return empty analysis
            print(f"Error extracting concepts: {str(e)}")
            return None

    async def close(self):
        """Cleanup resources."""
        await self.client.close()
