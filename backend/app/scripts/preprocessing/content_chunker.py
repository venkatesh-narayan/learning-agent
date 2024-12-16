import logging
from dataclasses import dataclass
from typing import List

logger = logging.getLogger(__name__)


@dataclass
class ContentChunk:
    """A chunk of content that fits within API limits."""

    text: str
    start_index: int  # Position in original text
    end_index: int


class ContentChunker:
    """Break down content into chunks suitable for API processing."""

    def __init__(self, max_chunk_size: int = 12000):
        self.max_chunk_size = max_chunk_size

    def chunk_content(self, text: str) -> List[ContentChunk]:
        """
        Split content into chunks that stay within API limits.
        """

        chunks = []
        current_pos = 0
        text_length = len(text)

        while current_pos < text_length:
            chunk_end = min(text_length, current_pos + self.max_chunk_size)

            chunks.append(
                ContentChunk(
                    text=text[current_pos:chunk_end],
                    start_index=current_pos,
                    end_index=chunk_end,
                )
            )

            current_pos = chunk_end

        logger.info(f"Split content into {len(chunks)} chunks")
        return chunks
