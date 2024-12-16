"""Run content processing pipeline on Modal."""

import asyncio
import base64
import json
import logging
import os
from typing import Dict

import modal
from app.scripts.gcs_utils import list_gcs_files, read_gcs_file, write_gcs_file
from app.services.preprocessing.chunk_processor import ChunkProcessor
from modal import Secret

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

# Create Modal app
app = modal.App("content-processor")

# Create image with required dependencies
image = modal.Image.debian_slim(python_version="3.10").pip_install(
    "beautifulsoup4",
    "google-cloud-storage",
    "openai",
    "pydantic",
    "pydantic-settings",
    "python-dotenv",
    "tenacity",
    "tqdm",
)


async def process_single_file(
    file_path: str,
    source_bucket: str,
    target_bucket: str,
    processor: ChunkProcessor,
) -> bool:
    """Process a single file and return True if successful."""
    try:
        # Read content
        raw_data = read_gcs_file(source_bucket, file_path)
        content_type = file_path.split("/")[1]  # e.g., "sec_filing"
        underlying_file_path = "/".join(file_path.split("/")[1:])

        # Process content
        processed_chunks = []
        async for chunk in processor.split_content(raw_data["content"], content_type):
            if chunk:
                processed_chunks.append(chunk)

        if not processed_chunks:
            logger.error(f"Failed to process {file_path}")
            return False

        # Prepare output
        output = {
            "content_id": file_path,
            "content_type": content_type,
            "metadata": {
                **raw_data.get("metadata", {}),
                "processing_metadata": [
                    processed.chunk_metadata for processed in processed_chunks
                ],
            },
            "analysis": {
                "content_analysis": [
                    processed.content_analysis.model_dump()
                    for processed in processed_chunks
                ],
                "topic_analysis": [
                    processed.topic_analysis.model_dump()
                    for processed in processed_chunks
                ],
            },
            "raw_content": raw_data,  # Keep original content
        }

        # Store processed result
        logger.info(f"Uploading {underlying_file_path} to {target_bucket}")
        write_gcs_file(target_bucket, underlying_file_path, output)
        logger.info(f"Successfully processed {file_path}")
        return True

    except Exception as e:
        logger.error(f"Error processing {file_path}: {str(e)}")
        return False


@app.function(
    image=image,
    secrets=[
        Secret.from_name("gcs-credentials-json"),
        Secret.from_name("openai-api-key"),
    ],
    timeout=7200,  # 2 hour timeout
    cpu=2,  # Use 2 CPUs
)
async def run_processing(batch_size: int = 10) -> Dict[str, int]:
    """Process content from GCS bucket."""

    # Set up GCS credentials
    creds_json = base64.b64decode(os.environ["credentials"])
    creds_dict = json.loads(creds_json)

    # Write credentials to temp file
    creds_path = "/tmp/gcs-credentials.json"
    with open(creds_path, "w") as f:
        json.dump(creds_dict, f)

    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path

    source_bucket = "scraped-financial-data"
    target_bucket = "scraped-financial-data/processed_content"

    try:
        # Initialize processor
        processor = ChunkProcessor(
            api_key=os.environ["openai_api_key"], max_concurrent=10
        )

        # Get files to process
        source_files = list_gcs_files(source_bucket, prefix="raw_data")

        # Filter out already processed
        processed_files = list_gcs_files(source_bucket, prefix="processed_content")

        no_prefix_source_files = [f.replace("raw_data/", "") for f in source_files]
        no_prefix_processed_files = [
            f.replace("processed_content/", "") for f in processed_files
        ]

        files_to_process = [
            os.path.join("raw_data", f)
            for f in no_prefix_source_files
            if f not in no_prefix_processed_files
        ]

        logger.info(
            f"Found {len(files_to_process)} files to process. "
            f"{len(processed_files)} already processed."
        )

        # Process in parallel batches
        stats = {"processed": 0, "errors": 0}

        for i in range(0, len(files_to_process), batch_size):
            batch = files_to_process[i : i + batch_size]  # noqa

            # Process batch
            results = await asyncio.gather(
                *[
                    process_single_file(
                        file_path=file_path,
                        source_bucket=source_bucket,
                        target_bucket=target_bucket,
                        processor=processor,
                    )
                    for file_path in batch
                ],
                return_exceptions=False,
            )

            # Update stats
            stats["processed"] += sum(1 for r in results if r)
            stats["errors"] += sum(1 for r in results if not r)

            # Log progress
            remaining = len(files_to_process) - i - len(batch)
            logger.info(
                f"Processed {stats['processed']} files with {stats['errors']} "
                f"errors. {remaining} files remaining."
            )

        return stats

    finally:
        # Cleanup
        if os.path.exists(creds_path):
            os.remove(creds_path)
