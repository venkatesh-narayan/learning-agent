import json
import os
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from app.scripts.scrapers.rss import RSSFeedScraper


@pytest.mark.asyncio
@patch("app.scripts.scrapers.base.storage.Client")
async def test_scraper(mock_storage_client):
    """Test RSS feed scraper functionality."""
    # Mock storage client
    mock_client = MagicMock()
    mock_storage_client.return_value = mock_client
    mock_bucket = MagicMock()
    mock_client.bucket.return_value = mock_bucket
    mock_blob = MagicMock()
    mock_bucket.blob.return_value = mock_blob

    # Get the directory containing this test file
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # Load test data
    with open(os.path.join(current_dir, "test_data/rss/test_rss_feed.json"), "r") as f:
        rss_data = json.load(f)

    # Create scraper instance with test API keys
    scraper = RSSFeedScraper(api_keys=["test_key_1", "test_key_2"])

    print("\nTesting API key to company distribution...")
    symbols = ["AAPL", "GOOGL", "MSFT", "AMZN"]
    company_assignments = scraper._assign_companies_to_keys(
        symbols, ["test_key_1", "test_key_2"]
    )
    print_company_assignments(company_assignments)
    # Verify API key to company distribution
    assert len(company_assignments) == 2, "Should assign 2 API keys"
    assert (
        len(company_assignments["test_key_1"]) == 2
    ), "First API key should have 2 companies"
    assert (
        len(company_assignments["test_key_2"]) == 2
    ), "Second API key should have 2 companies"
    # Verify company assignments
    all_companies = []
    for companies in company_assignments.values():
        all_companies.extend(companies)
    assert sorted(all_companies) == sorted(symbols), "All companies should be assigned"
    assert len(set(all_companies)) == len(symbols), "No duplicate company assignments"

    print("\nTesting batch creation...")
    batches = scraper._batch_symbols(symbols, batch_size=2)
    print_batches(batches)
    # Verify batch creation
    assert len(batches) == 2, "Should create 2 batches"
    assert len(batches[0]) == 2, "First batch should have 2 symbols"
    assert len(batches[1]) == 2, "Second batch should have 2 symbols"
    # Verify batch contents
    all_symbols = []
    for batch in batches:
        all_symbols.extend(batch)
    assert sorted(all_symbols) == sorted(symbols), "All symbols should be in batches"
    assert len(set(all_symbols)) == len(symbols), "No duplicate symbols in batches"

    print("\nTesting entry ID generation...")
    test_urls = [
        "https://example.com/feed/entry1",
        "https://example.com/feed/entry2",
        "https://example.com/feed/entry1",  # Duplicate URL
    ]
    entry_ids = [scraper._generate_entry_id(url) for url in test_urls]
    print("Generated entry IDs:", entry_ids)
    # Verify entry ID generation
    assert all(isinstance(id, str) for id in entry_ids), "All IDs should be strings"
    assert entry_ids[0] == entry_ids[2], "Same URL should generate same ID"
    assert entry_ids[0] != entry_ids[1], "Different URLs should generate different IDs"

    print("\nTesting feed parsing...")
    entries = await scraper._parse_feed(rss_data["feed_content"])
    print_entries(entries)
    # Verify feed parsing
    assert len(entries.get("entries", [])) == 2, "Should parse 2 entries"
    assert (
        entries.get("entries", [])[0].get("title", "")
        == "Apple Reports First Quarter Results"
    ), "First entry title should match"
    assert (
        entries.get("entries", [])[1].get("title", "")
        == "Apple Vision Pro Available February 2"
    ), "Second entry title should match"
    # Verify entry structure
    for entry in entries.get("entries", []):
        assert "title" in entry, "Entry should have title"
        assert "link" in entry, "Entry should have link"
        assert "published" in entry, "Entry should have published date"
        assert "summary" in entry, "Entry should have summary"

    print("\nTesting date parsing...")
    test_dates = rss_data["test_dates"]
    parsed_dates = []
    for test_date in test_dates:
        parsed_date = scraper._parse_date(test_date)
        parsed_dates.append(parsed_date)
        print(f"Original: {test_date}")
        print(f"Parsed: {parsed_date}")
        # Verify date parsing
        assert isinstance(
            parsed_date, datetime
        ), "Should parse date into datetime object"
        assert parsed_date.year == 2024, "Year should be 2024"
        assert parsed_date.month == 1, "Month should be January"
        assert parsed_date.day == 25, "Day should be 25th"
    # Verify date order
    assert all(
        d1 <= d2 for d1, d2 in zip(parsed_dates, parsed_dates[1:])
    ), "Dates should be in order"

    print("\nTesting company mention extraction...")
    mentions = scraper._extract_company_mentions(rss_data["test_content"])
    print_mentions(mentions)
    # Verify company mention extraction
    assert len(mentions) == 4, "Should extract 4 company mentions"
    assert mentions[0]["symbol"] == "AAPL", "First mention should be AAPL"
    assert mentions[1]["symbol"] == "MSFT", "Second mention should be MSFT"
    assert mentions[2]["symbol"] == "GOOGL", "Third mention should be GOOGL"
    assert mentions[3]["symbol"] == "AMZN", "Fourth mention should be AMZN"
    # Verify mention structure
    for mention in mentions:
        assert "symbol" in mention, "Mention should have symbol"
        assert "name" in mention, "Mention should have company name"
        assert isinstance(mention["symbol"], str), "Symbol should be string"
        assert isinstance(mention["name"], str), "Company name should be string"

    print("\nTesting entry storage...")
    success = await store_test_entries(scraper, rss_data)
    print(f"Entry storage {'successful' if success else 'failed'}")
    # Verify entry storage
    assert success, "Entry storage should be successful"


def print_company_assignments(assignments):
    """Print API key to company assignments."""
    print("\nAPI Key to Company Assignments:")
    for key, symbols in assignments.items():
        print(f"{key}: {', '.join(symbols)}")


def print_batches(batches):
    """Print symbol batches."""
    print("\nSymbol Batches:")
    for i, batch in enumerate(batches, 1):
        print(f"Batch {i}: {', '.join(batch)}")


def print_entries(entries):
    """Print parsed feed entries."""
    print("\nParsed Feed Entries:")
    for entry in entries.get("entries", []):
        print(f"\nTitle: {entry.get('title', 'No title')}")
        print(f"Link: {entry.get('link', 'No link')}")
        print(f"Published: {entry.get('published', 'No date')}")
        print(f"Summary: {entry.get('summary', 'No summary')[:100]}...")


def print_mentions(mentions):
    """Print company mentions."""
    print("\nCompany Mentions:")
    for mention in mentions:
        print(f"{mention['symbol']} ({mention['name']})")


async def store_test_entries(scraper, rss_data):
    """Test entry storage functionality."""
    try:
        for entry in rss_data["entries"]:
            await scraper._store_entry(
                entry=entry,
                feed_url="https://example.com/feed",
                company=entry.get("company"),
                published=scraper._parse_date(entry.get("published")),
                api_key="test_key_1",
            )
        return True
    except Exception as e:
        print(f"Error storing entries: {e}")
        return False


if __name__ == "__main__":
    import asyncio

    asyncio.run(test_scraper())
