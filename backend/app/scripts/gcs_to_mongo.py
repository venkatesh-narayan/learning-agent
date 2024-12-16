"""Script to transfer processed content from GCS to MongoDB."""

import asyncio
import logging
from typing import Any, Dict

from app.config import Settings
from app.scripts.gcs_utils import list_gcs_files, read_gcs_file
from motor.motor_asyncio import AsyncIOMotorClient
from tqdm import tqdm

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def setup_indexes(db):
    """Create necessary indexes for efficient querying."""
    try:
        # Content collection indexes
        await db.content.create_index("content_id", unique=True)
        await db.content.create_index("content_type")
        await db.content.create_index([("timestamp", -1)])

        # Analysis collection indexes
        await db.content_analysis.create_index([("content_id", 1), ("chunk_index", 1)])
        await db.topic_analysis.create_index([("content_id", 1), ("chunk_index", 1)])

        # Concept indexes for searching
        await db.content_analysis.create_index(
            [("main_concepts.name", 1), ("main_concepts.metrics", 1)]
        )

        # Topic indexes for searching
        await db.topic_analysis.create_index(
            [("primary_topic.name", 1), ("primary_topic.category", 1)]
        )

        logger.info("Successfully created all indexes")

    except Exception as e:
        logger.error(f"Error creating indexes: {str(e)}")
        raise


async def store_content_analyses(
    db, content_id: str, analyses: list[Dict[str, Any]]
) -> list[str]:
    """Store content analyses with their chunk index."""
    analysis_ids = []
    for idx, analysis in enumerate(analyses):
        analysis_doc = {"content_id": content_id, "chunk_index": idx, **analysis}
        result = await db.content_analysis.insert_one(analysis_doc)
        analysis_ids.append(str(result.inserted_id))
    return analysis_ids


async def store_topic_analyses(
    db, content_id: str, analyses: list[Dict[str, Any]]
) -> list[str]:
    """Store topic analyses with their chunk index."""
    analysis_ids = []
    for idx, analysis in enumerate(analyses):
        analysis_doc = {"content_id": content_id, "chunk_index": idx, **analysis}
        result = await db.topic_analysis.insert_one(analysis_doc)
        analysis_ids.append(str(result.inserted_id))
    return analysis_ids


async def upload_to_mongo(db, content: Dict[str, Any]) -> bool:
    """Upload processed content to MongoDB with its analyses."""
    try:
        # Store the content analyses
        content_analysis_ids = await store_content_analyses(
            db, content["content_id"], content["analysis"]["content_analysis"]
        )

        # Store the topic analyses
        topic_analysis_ids = await store_topic_analyses(
            db, content["content_id"], content["analysis"]["topic_analysis"]
        )

        # Create the main content document
        content_doc = {
            "content_id": content["content_id"],
            "content_type": content["content_type"],
            "metadata": content["metadata"],
            "content_analysis_ids": content_analysis_ids,
            "topic_analysis_ids": topic_analysis_ids,
            "raw_content": content["raw_content"],
            "timestamp": content["metadata"].get("scraped_at"),
        }

        # Store the main content
        await db.content.insert_one(content_doc)
        return True

    except Exception as e:
        logger.error(f"Error uploading content {content['content_id']}: {str(e)}")
        return False


async def main():
    """Run the transfer process."""
    # Load settings
    settings = Settings()

    # Initialize MongoDB client - use financial_content database
    mongo_client = AsyncIOMotorClient(settings.mongodb_uri)
    db = mongo_client.financial_content

    # Set up indexes
    await setup_indexes(db)

    # Get list of processed files from GCS
    processed_files = list_gcs_files(settings.gcs_bucket, prefix="processed_content")
    logger.info(f"Found {len(processed_files)} processed files")

    # Process files
    stats = {"processed": 0, "errors": 0}

    for file_path in tqdm(processed_files, desc="Uploading to MongoDB"):
        try:
            # Read content from GCS
            content = read_gcs_file(settings.gcs_bucket, file_path)

            # Upload to MongoDB
            success = await upload_to_mongo(db, content)
            if success:
                stats["processed"] += 1
            else:
                stats["errors"] += 1

        except Exception as e:
            logger.error(f"Error processing {file_path}: {str(e)}")
            stats["errors"] += 1

    logger.info(
        f"Transfer complete. Processed {stats['processed']} files with "
        f"{stats['errors']} errors."
    )

    # Print some stats about what was stored
    try:
        content_count = await db.content.count_documents({})
        content_analysis_count = await db.content_analysis.count_documents({})
        topic_analysis_count = await db.topic_analysis.count_documents({})

        logger.info("\nDatabase contents:")
        logger.info(f"Total documents: {content_count}")
        logger.info(f"Content analyses: {content_analysis_count}")
        logger.info(f"Topic analyses: {topic_analysis_count}")

        # Sample some content types
        content_types = await db.content.distinct("content_type")
        logger.info(f"\nContent types: {content_types}")

        for ct in content_types:
            count = await db.content.count_documents({"content_type": ct})
            logger.info(f"{ct}: {count} documents")

    except Exception as e:
        logger.error(f"Error getting stats: {str(e)}")


if __name__ == "__main__":
    asyncio.run(main())
