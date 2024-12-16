import json
import os
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from aioresponses import aioresponses
from app.scripts.scrapers.sec import SECFilingScraper


@pytest.mark.asyncio
@patch("app.scripts.scrapers.base.storage.Client")
async def test_scraper(mock_storage_client):
    """Test SEC filing storage."""
    # Mock storage client
    mock_client = MagicMock()
    mock_storage_client.return_value = mock_client
    mock_bucket = MagicMock()
    mock_client.bucket.return_value = mock_bucket
    mock_blob = MagicMock()
    mock_blob.exists.return_value = False  # File doesn't exist, so we should store it
    mock_bucket.blob.return_value = mock_blob

    # Get the directory containing this test file
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # Initialize scraper with test user agent
    test_user_agent = "test_agent"
    scraper = SECFilingScraper(user_agents=[test_user_agent])

    # Test storing 10-Q filing
    with open(os.path.join(current_dir, "test_data/sec/test_10q.json"), "r") as f:
        data = json.load(f)
        content = data["content"]["filing_html"]

    # Create a real aiohttp session for testing
    async with aiohttp.ClientSession() as session:
        # Mock HTTP responses using aioresponses
        with aioresponses() as m:
            # Mock the filing URL
            filing_url = "https://www.sec.gov/Archives/edgar/data/0000123456/000012345622123456/test.htm"  # noqa
            m.get(filing_url, status=200, body=content)

            # Mock rate limiter to return our test agent
            with patch.object(scraper.rate_limiter, "acquire") as mock_acquire:
                mock_acquire.return_value = test_user_agent

                # Mock store_raw_content to return True
                mock_store = AsyncMock(return_value=True)
                with patch.object(scraper, "store_raw_content", new=mock_store):
                    # Test scraping a 10-Q filing
                    filing_date = datetime(2024, 1, 1)  # Use a fixed date for testing
                    result = await scraper._scrape_filing(
                        session=session,
                        company={
                            "symbol": "TEST",
                            "name": "Test Company",
                            "sector": "Technology",
                        },
                        cik="0000123456",
                        accession="000012345622123456",
                        primary_doc="test.htm",
                        form_type="10-Q",
                        filing_date=filing_date,
                        filing_id="test_filing_id",
                        user_agent=test_user_agent,
                    )

                    # Verify the result
                    assert result == ("10-Q", True), "Should successfully process 10-Q"

                    # Verify store_raw_content was called with correct arguments
                    mock_store.assert_called_once()
                    call_args = mock_store.call_args[1]  # Get kwargs
                    assert call_args["content_type"] == "sec_filing"
                    assert call_args["identifier"] == "test_filing_id"
                    assert call_args["raw_content"]["filing_type"] == "10-Q"
                    assert call_args["raw_content"]["filing_html"] == content
                    assert "url" in call_args["raw_content"]

                    # Verify metadata
                    metadata = call_args["metadata"]
                    assert metadata["symbol"] == "TEST"
                    assert metadata["company_name"] == "Test Company"
                    assert metadata["sector"] == "Technology"
                    assert metadata["filing_type"] == "10-Q"
                    assert metadata["cik"] == "0000123456"
                    assert metadata["accession"] == "000012345622123456"
                    assert metadata["api_key_used"] == test_user_agent
                    assert metadata["filing_date"] == filing_date.isoformat()
