import asyncio
import base64
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict  # , List, Optional

import modal
from app.scripts.scrapers import (
    EarningsCallScraper,
    NewsAPIScraper,
    PolygonScraper,
    RSSFeedScraper,
    SECFilingScraper,
)
from modal import Secret

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Create Modal app
app = modal.App("financial-content-scraper")

# Create image with required dependencies
image = (
    modal.Image.debian_slim(python_version="3.10")
    .pip_install(
        "aiohttp",
        "beautifulsoup4",
        "feedparser",
        "google-cloud-storage",
        "spacy",
        "pyyaml",
    )
    .run_commands(
        # Install spaCy model
        "python -m spacy download en_core_web_lg",
    )
)


logger = logging.getLogger(__name__)


@app.function(
    image=image,
    secrets=[
        Secret.from_name("gcs-credentials-json"),
        Secret.from_name("seeking-alpha-keys"),
        Secret.from_name("newsapi-keys"),
        Secret.from_name("sec-user-agents"),
        Secret.from_name("polygon-api-keys"),
    ],
    timeout=7200,  # 2 hour timeout (increased from 1 hour)
)
async def run_scrapers(
    days_back: int = 90,  # Changed from 30 to 90 days to get more filings
    symbols=None,  # Optional[List[str]] = None,
    prioritize_sectors=None,  #: Optional[List[str]] = None,
) -> Dict[str, Dict[str, int]]:
    """Run all scrapers to collect financial content."""

    # Set up dates
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)

    # Initialize results collection
    results = {}

    # GCS configuration
    bucket_name = "scraped-financial-data"

    # Set up GCS credentials
    creds_json = base64.b64decode(os.environ["credentials"])
    creds_dict = json.loads(creds_json)

    # Write credentials to a temporary file that GCS client will use
    creds_path = "/tmp/gcs-credentials.json"
    with open(creds_path, "w") as f:
        json.dump(creds_dict, f)

    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path

    # Load API keys from secrets - using unique key names
    seeking_alpha_keys = os.environ["seeking_alpha_keys"].split(",")
    newsapi_keys = os.environ["newsapi_keys"].split(",")
    sec_user_agents = os.environ["sec_agents"].split(",")
    polygon_api_keys = os.environ["polygon_keys"].split(",")

    try:
        # Initialize scrapers with timeouts
        scrapers = {
            "SEC Filings": SECFilingScraper(
                user_agents=sec_user_agents,
                bucket_name=bucket_name,
            ),
            "Earnings Calls": EarningsCallScraper(
                api_keys=seeking_alpha_keys,
                bucket_name=bucket_name,
            ),
            "News": NewsAPIScraper(
                api_keys=newsapi_keys,
                bucket_name=bucket_name,
            ),
            "Press Releases": RSSFeedScraper(
                api_keys=[],  # No authentication needed
                bucket_name=bucket_name,
                max_concurrent=3,  # Reduced from 5 to be more conservative
            ),
            "Market Data": PolygonScraper(
                api_keys=polygon_api_keys,
                bucket_name=bucket_name,
            ),
        }

        # Run scrapers with timeouts
        for name, scraper in scrapers.items():
            try:
                logger.info(f"Running {name} scraper...")
                scrape_result = await asyncio.wait_for(
                    scraper.scrape(
                        start_date=start_date,
                        end_date=end_date,
                        symbols=symbols,
                        prioritize_sectors=prioritize_sectors,
                    ),
                    timeout=3600,  # 1 hour timeout per scraper
                )
                results[name] = scrape_result

                # Log GCS upload statistics
                upload_stats = scraper.get_upload_stats()
                logger.info(
                    f"[GCS] {name} upload stats: "
                    f"Success={upload_stats.get('success', 0)}, "
                    f"Skipped={upload_stats.get('skipped', 0)}, "
                    f"Failed={upload_stats.get('failed', 0)}"
                )

            except asyncio.TimeoutError:
                logger.error(f"Timeout running {name} scraper")
                results[name] = {"error": "Timeout"}
            except Exception as e:
                logger.error(f"Error running {name} scraper: {str(e)}")
                results[name] = {"error": str(e)}

            finally:
                await scraper.close()

    except Exception as e:
        logger.error(f"Error in scraper orchestration: {str(e)}")
        return {"error": str(e)}
    finally:
        # Clean up credentials file
        if os.path.exists(creds_path):
            os.remove(creds_path)

    return results
