"""Shared pytest fixtures for x-news-skills tests."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add src to path for imports
SRC_PATH = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC_PATH))


@pytest.fixture
def fixtures_dir():
    """Path to fixtures directory."""
    return Path(__file__).parent / "fixtures"


# ---- Raw JSON fixtures ----


@pytest.fixture
def valid_tweets(fixtures_dir):
    """Load valid raw tweets fixture."""
    with open(fixtures_dir / "raw" / "valid_tweets.json") as f:
        return json.load(f)


@pytest.fixture
def malformed_tweets():
    """JSON that parses but contains non-dict values (the x_list_fetch bug case)."""
    return [1, 2, "string", None, {"id": "123"}]


@pytest.fixture
def empty_tweets():
    """Empty tweets array."""
    return []


# ---- Filtered JSON fixtures ----


@pytest.fixture
def valid_filtered(fixtures_dir):
    """Load valid filtered.json fixture."""
    with open(fixtures_dir / "filtered" / "valid_filtered.json") as f:
        return json.load(f)


@pytest.fixture
def empty_filtered():
    """Empty filtered result."""
    return {
        "stats": {
            "total_raw": 0,
            "unique": 0,
            "within_window": 0,
            "grouped_candidates": 0,
            "strong": 0,
            "medium": 0,
            "backfill": 0,
            "skipped": 0,
            "skipped_breakdown": {},
        },
        "strong": [],
        "medium": [],
        "backfill": [],
    }


# ---- Companion JSON fixtures ----


@pytest.fixture
def valid_companion(fixtures_dir):
    """Load valid companion.json fixture."""
    with open(fixtures_dir / "companion" / "valid_companion.json") as f:
        return json.load(f)


# ---- Post JSON fixtures ----


@pytest.fixture
def valid_post(fixtures_dir):
    """Load valid post.json fixture."""
    with open(fixtures_dir / "post" / "valid_post.json") as f:
        return json.load(f)


# ---- Mock fixtures for external CLI calls ----


@pytest.fixture
def mock_twitter_cli_success():
    """Mock successful twitter CLI response (JSONL format)."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"id": "123", "url": "https://x.com/user/status/123", '
            '"author": "user", "text": "test tweet", "time": "2024-01-01T00:00:00Z", '
            '"likes": 100, "views": 1000, "bookmarks": 50}\n',
            stderr="",
        )
        yield mock_run


@pytest.fixture
def mock_twitter_cli_failure():
    """Mock failing twitter CLI response."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Error: rate limited",
        )
        yield mock_run


@pytest.fixture
def mock_twitter_cli_jsonl_with_non_dict():
    """Mock twitter CLI returning JSONL with non-dict values (the bug case)."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"id": "123", "text": "valid"}\n1\n"string"\nnull\n{"id": "456", "text": "also valid"}\n',
            stderr="",
        )
        yield mock_run


@pytest.fixture
def mock_gh_cli_success():
    """Mock successful gh CLI response."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='{"description": "Test repo", "stargazerCount": 100}',
            stderr="",
        )
        yield mock_run


@pytest.fixture
def mock_web_fetch_success():
    """Mock successful web fetch."""
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_response = MagicMock()
        mock_response.read.return_value = b"<html><title>Test Page</title></html>"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response
        yield mock_urlopen


# ---- Now fixture ----


@pytest.fixture
def now():
    """Current UTC datetime for testing."""
    return datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
