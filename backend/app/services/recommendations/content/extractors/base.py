from abc import ABC, abstractmethod
from typing import Optional

from app.models.recommendations.content import ProcessedContent


class ContentExtractor(ABC):
    """Base class for content extraction."""

    @abstractmethod
    async def extract(
        self, content_id: str, url: str, html: str
    ) -> Optional[ProcessedContent]:
        """
        Extract structured information from content.
        Each content type implements its own extraction logic.
        """
        pass
