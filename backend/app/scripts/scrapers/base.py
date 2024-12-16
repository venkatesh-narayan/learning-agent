import gzip
import json
import logging
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, Optional

from google.cloud import storage

logger = logging.getLogger(__name__)


class BaseScraper:
    """Base class for all scrapers with GCS integration."""

    def __init__(self, bucket_name: str = "scraped-financial-data"):
        self.bucket_name = bucket_name
        try:
            self.storage_client = storage.Client()
            self.bucket = self.storage_client.bucket(bucket_name)
            logger.info(f"[GCS] Successfully initialized bucket: {bucket_name}")
        except Exception as e:
            logger.error(f"[GCS] Failed to initialize GCS client: {str(e)}")
            raise

        # Track successful uploads
        self.upload_stats = defaultdict(int)

    def _get_storage_path(self, content_type: str, identifier: str) -> str:
        """Get GCS path for content."""
        date = datetime.now()
        return (
            f"{content_type}/"
            f"{date.year}/{date.month:02d}/{date.day:02d}/"
            f"{identifier}.json.gz"
        )

    async def store_raw_content(
        self, content_type: str, identifier: str, raw_content: Any, metadata: Dict
    ) -> bool:
        """
        Store raw content in GCS.

        Args:
            content_type: Type of content (e.g., 'sec_filing', 'earnings_call')
            identifier: Unique identifier for the content
            raw_content: Raw content exactly as received
            metadata: Additional content metadata
        """
        try:
            # Generate GCS path
            storage_path = self._get_storage_path(content_type, identifier)
            logger.info(f"[GCS] Attempting to store {content_type} at {storage_path}")

            # Prepare the full document
            document = {
                "content": raw_content,
                "metadata": {
                    **metadata,
                    "content_type": content_type,
                    "identifier": identifier,
                    "scraped_at": datetime.now().isoformat(),
                    "storage_path": storage_path,
                },
            }

            # Check if content already exists
            blob = self.bucket.blob(storage_path)
            if blob.exists():
                logger.info(f"[GCS] Content already exists: {storage_path}")
                self.upload_stats["skipped"] += 1
                return True

            # Compress the full document
            content_str = json.dumps(document)
            compressed = gzip.compress(content_str.encode("utf-8"))
            logger.info(f"[GCS] Compressed content size: {len(compressed)} bytes")

            # Upload to GCS
            blob.upload_from_string(compressed, content_type="application/gzip")
            logger.info(
                f"[GCS] Successfully uploaded {content_type} to {storage_path}"
            )
            self.upload_stats["success"] += 1

            return True

        except Exception as e:
            logger.error(
                f"[GCS] Error storing {content_type} {identifier} at "
                f"{storage_path}: {str(e)}"
            )
            self.upload_stats["failed"] += 1
            return False

    async def get_raw_content(self, storage_path: str) -> Optional[Dict]:
        """Retrieve stored raw content from GCS."""
        try:
            logger.info(f"[GCS] Attempting to retrieve content from {storage_path}")
            blob = self.bucket.blob(storage_path)
            if not blob.exists():
                logger.info(f"[GCS] Content not found at {storage_path}")
                return None

            # Download and decompress
            compressed = blob.download_as_bytes()
            content = json.loads(gzip.decompress(compressed).decode("utf-8"))
            logger.info(f"[GCS] Successfully retrieved content from {storage_path}")
            return content

        except Exception as e:
            logger.error(
                f"[GCS] Error retrieving content from {storage_path}: {str(e)}"
            )
            return None

    def get_upload_stats(self) -> Dict[str, int]:
        """Get statistics about GCS uploads."""
        return dict(self.upload_stats)
