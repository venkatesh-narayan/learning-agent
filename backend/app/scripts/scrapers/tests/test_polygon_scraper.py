import asyncio
import json
import os
from unittest.mock import MagicMock, patch

import pytest
from app.scripts.scrapers.polygon import PolygonScraper


@pytest.mark.asyncio
@patch("google.cloud.storage.Client")
async def test_scraper(mock_storage_client):
    """Test Polygon.io scraper functionality."""
    # Mock GCS client
    mock_bucket = MagicMock()
    mock_storage_client.return_value.bucket.return_value = mock_bucket

    # Get the directory containing this test file
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # Load test data
    with open(
        os.path.join(current_dir, "test_data/polygon/test_polygon_details.json"), "r"
    ) as f:
        details_data = json.load(f)

    with open(
        os.path.join(current_dir, "test_data/polygon/test_polygon_financials.json"),
        "r",
    ) as f:
        financials_data = json.load(f)

    # Create scraper instance with test API keys
    scraper = PolygonScraper(api_keys=["test_key_1", "test_key_2"])

    print("\nTesting API key distribution...")
    symbols = ["AAPL", "GOOGL", "MSFT", "AMZN"]
    assignments = scraper._assign_companies_to_keys(symbols)
    print_assignments(assignments)

    print("\nTesting batch creation...")
    batches = scraper._batch_symbols(symbols, batch_size=2)
    print_batches(batches)

    print("\nTesting company details extraction...")
    details_success = await process_company_details(scraper, details_data)
    print(f"Details extraction {'successful' if details_success else 'failed'}")

    print("\nTesting financial statements extraction...")
    financials_success = await process_financials(scraper, financials_data)
    print(f"Financials extraction {'successful' if financials_success else 'failed'}")


def print_assignments(assignments):
    """Print API key assignments."""
    print("\nAPI Key Assignments:")
    for key, symbols in assignments.items():
        print(f"{key}: {', '.join(symbols)}")


def print_batches(batches):
    """Print symbol batches."""
    print("\nSymbol Batches:")
    for i, batch in enumerate(batches):
        print(f"Batch {i + 1}: {', '.join(batch)}")


async def process_company_details(scraper, test_data):
    """Test company details processing."""
    try:
        content = {
            "company_details": test_data["results"],
            "recent_news": test_data.get("news", {}).get("results", []),
        }

        await scraper.store_raw_content(
            content_type="company_details",
            identifier="test_polygon_details_AAPL",
            raw_content=content,
            metadata={
                "symbol": "AAPL",
                "company_name": "Apple Inc.",
                "sector": "Technology",
                "api_key_used": "test_key_1",
            },
        )
        return True
    except Exception as e:
        print(f"Error processing company details: {str(e)}")
        return False


async def process_financials(scraper, test_data):
    """Test financials processing."""
    try:
        await scraper.store_raw_content(
            content_type="financials",
            identifier="test_polygon_financials_AAPL_2024Q1",
            raw_content=test_data,
            metadata={
                "symbol": "AAPL",
                "company_name": "Apple Inc.",
                "sector": "Technology",
                "api_key_used": "test_key_1",
                "quarter": "2024Q1",
            },
        )
        return True
    except Exception as e:
        print(f"Error processing financials: {str(e)}")
        return False


if __name__ == "__main__":
    asyncio.run(test_scraper())
