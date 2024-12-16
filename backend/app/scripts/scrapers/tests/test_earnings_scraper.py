import json
import os
from unittest.mock import MagicMock, patch

import pytest
from app.scripts.scrapers.earnings import EarningsCallScraper


@pytest.mark.asyncio
@patch("app.scripts.scrapers.base.storage.Client")
async def test_scraper(mock_storage_client):
    """Test earnings call scraper functionality."""
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
        os.path.join(current_dir, "test_data/earnings/test_earnings_transcript.json"),
        "r",
    ) as f:
        transcript_data = json.load(f)

    # Create scraper instance with test API keys
    scraper = EarningsCallScraper(api_keys=["test_key_1", "test_key_2"])

    print("\nTesting API key distribution...")
    symbols = ["AAPL", "GOOGL", "MSFT", "AMZN"]
    assignments = scraper._assign_companies_to_keys(symbols)
    print_assignments(assignments)
    # Verify API key distribution
    assert len(assignments) == 2, "Should distribute companies across 2 API keys"
    assert all(
        len(companies) == 2 for companies in assignments.values()
    ), "Each API key should have 2 companies"
    # Verify company assignments
    all_companies = []
    for companies in assignments.values():
        all_companies.extend(companies)
    assert sorted(all_companies) == sorted(symbols), "All companies should be assigned"
    assert len(set(all_companies)) == len(symbols), "No duplicate company assignments"

    print("\nTesting batch creation...")
    batches = scraper._batch_symbols(symbols, batch_size=2)
    print_batches(batches)
    # Verify batch creation
    assert len(batches) == 2, "Should create 2 batches"
    assert all(
        len(batch) == 2 for batch in batches
    ), "Each batch should have 2 symbols"
    # Verify batch contents
    all_symbols = []
    for batch in batches:
        all_symbols.extend(batch)
    assert sorted(all_symbols) == sorted(symbols), "All symbols should be in batches"
    assert len(set(all_symbols)) == len(symbols), "No duplicate symbols in batches"

    print("\nTesting transcript ID generation...")
    test_cases = [
        ("AAPL", "12345"),
        ("GOOGL", "67890"),
        ("AAPL", "12345"),  # Duplicate
    ]
    transcript_ids = [
        scraper._generate_transcript_id(symbol, call_id)
        for symbol, call_id in test_cases
    ]
    print("Generated transcript IDs:", transcript_ids)
    # Verify transcript ID format and uniqueness
    assert all(
        id.startswith("earnings_") for id in transcript_ids
    ), "IDs should start with 'earnings_'"
    assert (
        transcript_ids[0] == transcript_ids[2]
    ), "Same inputs should generate same ID"
    assert (
        transcript_ids[0] != transcript_ids[1]
    ), "Different inputs should generate different IDs"
    assert all(
        "_" in id for id in transcript_ids
    ), "IDs should contain underscore separators"

    print("\nTesting speaker segment extraction...")
    speaker_segments = scraper._extract_speaker_segments(
        transcript_data["presentation"]
    )
    print_speaker_segments(speaker_segments)
    # Verify speaker segments
    assert len(speaker_segments) == 3, "Should extract 3 speaker segments"
    assert (
        speaker_segments[0]["speaker"] == "Operator"
    ), "First speaker should be Operator"
    assert (
        speaker_segments[1]["speaker"] == "Tim Cook"
    ), "Second speaker should be Tim Cook"
    assert (
        speaker_segments[2]["speaker"] == "Luca Maestri"
    ), "Third speaker should be Luca Maestri"
    # Verify segment structure
    for segment in speaker_segments:
        assert "speaker" in segment, "Segment should have speaker"
        assert "content" in segment, "Segment should have content"
        assert isinstance(segment["speaker"], str), "Speaker should be string"
        assert isinstance(segment["content"], str), "Content should be string"
        assert len(segment["content"]) > 0, "Content should not be empty"

    print("\nTesting Q&A segment extraction...")
    qa_segments = scraper._extract_qa_segments(transcript_data["qa_session"])
    print_qa_segments(qa_segments)
    # Verify Q&A segments
    assert len(qa_segments) == 2, "Should extract 2 Q&A segments"
    # Verify first Q&A segment
    assert (
        qa_segments[0]["question"]["speaker"] == "Katy Huberty"
    ), "First question should be from Katy Huberty"
    assert len(qa_segments[0]["answers"]) == 2, "First Q&A should have 2 answers"
    assert (
        qa_segments[0]["answers"][0]["speaker"] == "Tim Cook"
    ), "First answer should be from Tim Cook"
    # Verify second Q&A segment
    assert (
        qa_segments[1]["question"]["speaker"] == "Toni Sacconaghi"
    ), "Second question should be from Toni Sacconaghi"
    assert len(qa_segments[1]["answers"]) == 1, "Second Q&A should have 1 answer"
    assert (
        qa_segments[1]["answers"][0]["speaker"] == "Luca Maestri"
    ), "Answer should be from Luca Maestri"
    # Verify Q&A structure
    for segment in qa_segments:
        assert "question" in segment, "Segment should have question"
        assert "answers" in segment, "Segment should have answers"
        assert isinstance(segment["question"], dict), "Question should be dictionary"
        assert isinstance(segment["answers"], list), "Answers should be list"
        assert "speaker" in segment["question"], "Question should have speaker"
        assert "content" in segment["question"], "Question should have content"
        for answer in segment["answers"]:
            assert "speaker" in answer, "Answer should have speaker"
            assert "content" in answer, "Answer should have content"
            assert isinstance(
                answer["content"], str
            ), "Answer content should be string"
            assert len(answer["content"]) > 0, "Answer content should not be empty"

    print("\nTesting section extraction...")
    sections = await scraper._extract_sections(transcript_data)
    print_sections(sections)
    # Verify sections
    assert len(sections) == 3, "Should extract 3 sections"
    # Verify section types
    assert (
        sections[0]["type"] == "participants"
    ), "First section should be participants"
    assert (
        sections[1]["type"] == "presentation"
    ), "Second section should be presentation"
    assert sections[2]["type"] == "qa", "Third section should be Q&A"
    # Verify section structure
    for section in sections:
        assert "title" in section, "Section should have title"
        assert "content" in section, "Section should have content"
        assert "type" in section, "Section should have type"
        assert "metadata" in section, "Section should have metadata"
        assert isinstance(section["title"], str), "Title should be string"
        assert isinstance(section["content"], str), "Content should be string"
        assert isinstance(section["type"], str), "Type should be string"
        assert isinstance(section["metadata"], dict), "Metadata should be dictionary"


def print_assignments(assignments):
    """Print API key assignments."""
    print("\nAPI Key Assignments:")
    for key, companies in assignments.items():
        print(f"{key}: {', '.join(companies)}")


def print_batches(batches):
    """Print symbol batches."""
    print("\nSymbol Batches:")
    for i, batch in enumerate(batches, 1):
        print(f"Batch {i}: {', '.join(batch)}")


def print_speaker_segments(segments):
    """Print speaker segments."""
    print("\nSpeaker Segments:")
    for segment in segments:
        print(f"\nSpeaker: {segment['speaker']}")
        print(f"Content: {segment['content'][:100]}...")


def print_qa_segments(segments):
    """Print Q&A segments."""
    print("\nQ&A Segments:")
    for segment in segments:
        for answer in segment["answers"]:
            if "question" in answer:
                print(f"\nQuestion: {answer['question']}")
            print(f"Answer by {answer['speaker']}: {answer['content'][:100]}...")


def print_sections(sections):
    """Print transcript sections."""
    print("\nTranscript Sections:")
    for section in sections:
        print(f"\nType: {section['type']}")
        print(f"Title: {section['title']}")
        print(f"Content length: {len(section['content'])} characters")
        print(f"First 100 chars: {section['content'][:100]}...")


if __name__ == "__main__":
    import asyncio

    asyncio.run(test_scraper())
