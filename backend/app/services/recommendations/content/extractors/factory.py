from typing import Optional

from app.services.content.extractors.base import ContentExtractor
from app.services.content.extractors.financial import FinancialContentExtractor


def create_extractor(segment: str = "financial") -> Optional[ContentExtractor]:
    """Create appropriate extractor for content segment."""
    extractors = {
        "financial": FinancialContentExtractor,
        # Add more segments as needed
    }

    extractor_class = extractors.get(segment)
    if extractor_class:
        return extractor_class()

    raise ValueError(f"Unsupported content segment: {segment}")
