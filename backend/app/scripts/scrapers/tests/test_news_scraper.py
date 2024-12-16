import json
import os
from unittest.mock import MagicMock, patch

import pytest
from app.scripts.scrapers.news import NewsAPIScraper


@pytest.mark.asyncio
@patch("app.scripts.scrapers.base.storage.Client")
async def test_scraper(mock_storage_client):
    """Test NewsAPI scraper functionality."""
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
    with open(
        os.path.join(current_dir, "test_data/news/test_news_articles.json"), "r"
    ) as f:
        news_data = json.load(f)

    # Create scraper instance with test API keys
    scraper = NewsAPIScraper(api_keys=["test_key_1", "test_key_2"])

    print("\nTesting API key to query distribution...")
    query_assignments = scraper._assign_queries_to_keys()
    print_query_assignments(query_assignments)
    # Verify API key to query distribution
    assert len(query_assignments) == 2, "Should distribute queries across 2 API keys"
    assert all(
        len(queries) == 5 for queries in query_assignments.values()
    ), "Each API key should have 5 queries"
    # Verify query content
    for key, queries in query_assignments.items():
        assert all(
            isinstance(q, str) for q in queries
        ), "All queries should be strings"
        assert all(len(q) > 0 for q in queries), "No empty queries allowed"

    print("\nTesting API key to company distribution...")
    symbols = ["AAPL", "GOOGL", "MSFT", "AMZN"]
    company_assignments = scraper._assign_companies_to_keys(symbols)
    print_company_assignments(company_assignments)
    # Verify API key to company distribution
    assert (
        len(company_assignments) == 2
    ), "Should distribute companies across 2 API keys"
    assert all(
        len(companies) == 2 for companies in company_assignments.values()
    ), "Each API key should have 2 companies"
    # Verify company assignments
    all_companies = []
    for companies in company_assignments.values():
        all_companies.extend(companies)
    assert sorted(all_companies) == sorted(symbols), "All companies should be assigned"
    assert len(set(all_companies)) == len(symbols), "No duplicate company assignments"

    print("\nTesting article ID generation...")
    test_urls = [
        "https://example.com/article1",
        "https://example.com/article2",
        "https://example.com/article1",  # Duplicate URL
    ]
    article_ids = [scraper._generate_article_id(url) for url in test_urls]
    print("Generated article IDs:", article_ids)
    # Verify article ID format and uniqueness
    assert all(
        id.startswith("news_") for id in article_ids
    ), "All IDs should start with 'news_'"
    assert all(len(id) > 10 for id in article_ids), "IDs should be sufficiently long"
    assert article_ids[0] == article_ids[2], "Same URL should generate same ID"
    assert (
        article_ids[0] != article_ids[1]
    ), "Different URLs should generate different IDs"

    print("\nTesting article storage...")
    success = await store_test_articles(scraper, news_data)
    print(f"Article storage {'successful' if success else 'failed'}")
    # Verify article storage
    assert success, "Article storage should be successful"
    # Verify article content
    for article in news_data["articles"]:
        assert "title" in article, "Article should have title"
        assert "url" in article, "Article should have URL"
        assert (
            "description" in article or "content" in article
        ), "Article should have content"
        if "company" in article:
            assert (
                article["company"]["symbol"] in symbols
            ), "Company symbol should be in valid symbols list"


def print_query_assignments(assignments):
    """Print API key to query assignments."""
    print("\nAPI Key to Query Assignments:")
    for key, queries in assignments.items():
        print(f"{key}:")
        for query in queries:
            print(f"  - {query}")


def print_company_assignments(assignments):
    """Print API key to company assignments."""
    print("\nAPI Key to Company Assignments:")
    for key, symbols in assignments.items():
        print(f"{key}: {', '.join(symbols)}")


async def store_test_articles(scraper, news_data):
    """Test article storage functionality."""
    try:
        for article in news_data["articles"]:
            article_id = scraper._generate_article_id(article["url"])

            # Store company-specific article
            if "company" in article:
                await scraper._store_article(
                    article=article,
                    article_id=article_id,
                    company=article["company"],
                    api_key="test_key_1",
                )
            # Store general financial news article
            else:
                await scraper._store_article(
                    article=article,
                    article_id=article_id,
                    company=None,
                    api_key="test_key_1",
                )
        return True
    except Exception as e:
        print(f"Error storing articles: {e}")
        return False


if __name__ == "__main__":
    import asyncio

    asyncio.run(test_scraper())
