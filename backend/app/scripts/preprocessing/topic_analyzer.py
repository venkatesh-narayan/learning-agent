from typing import Optional

from app.models.topic_analysis import TopicAnalysis
from app.prompts import PROMPTS
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential


class TopicAnalyzer:
    """Analyze topics and themes in financial content using LLM."""

    def __init__(self, model: str = "gpt-4o-mini"):
        self.client = AsyncOpenAI()
        self.model = model

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True,
    )
    async def analyze_topics(self, text: str) -> Optional[TopicAnalysis]:
        """Analyze topics and themes in text."""
        try:
            response = await self.client.beta.chat.completions.parse(
                model=self.model,
                temperature=0,
                messages=[
                    {
                        "role": "system",
                        "content": PROMPTS["system"]["content_preprocessing"][
                            "topic_analysis"
                        ],
                    },
                    {
                        "role": "user",
                        "content": PROMPTS["user"]["content_preprocessing"][
                            "topic_analysis"
                        ].format(text=text),
                    },
                ],
                response_format=TopicAnalysis,
            )

            return response.choices[0].message.parsed

        except Exception as e:
            print(f"Error analyzing topics: {str(e)}")
            return None

    async def close(self):
        """Cleanup resources."""
        await self.client.close()
