"""Tests for x_list_fetch.py."""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPTS_PATH = (
    Path(__file__).parent.parent.parent.parent / "skills" / "x-news-data-pipeline" / "scripts"
)
sys.path.insert(0, str(SCRIPTS_PATH))

from x_list_fetch import deduplicate_tweets, fetch_all_lists, fetch_list_tweets, parse_iso


def list_envelope(items: list[object], *, ok: bool = True, error: dict | None = None) -> str:
    """Return a twitter-cli style JSON envelope."""
    payload = {"ok": ok, "data": items}
    if error is not None:
        payload["error"] = error
    return json.dumps(payload, ensure_ascii=False)


class TestFetchListTweets:
    """Test twitter-cli envelope parsing and failure handling."""

    def test_successful_envelope_filters_non_dict_items(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=list_envelope(
                    [
                        {"id": "123", "text": "valid"},
                        1,
                        "string",
                        None,
                        {"id": "456", "text": "also valid"},
                    ]
                ),
                stderr="",
            )

            tweets = fetch_list_tweets("list123", 50)

            assert len(tweets) == 2
            assert all(isinstance(tweet, dict) for tweet in tweets)
            assert tweets[0]["id"] == "123"
            assert tweets[1]["id"] == "456"

    def test_empty_stdout_returns_empty_list(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

            tweets = fetch_list_tweets("list123", 50)

            assert tweets == []

    def test_failure_returns_empty_list(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Error")

            tweets = fetch_list_tweets("list123", 50)

            assert tweets == []

    def test_invalid_json_returns_empty_list(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="{not-json", stderr="")

            tweets = fetch_list_tweets("list123", 50)

            assert tweets == []

    def test_api_error_envelope_returns_empty_list(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout=list_envelope(
                    [],
                    ok=False,
                    error={"code": "rate_limited", "message": "Rate limit exceeded"},
                ),
                stderr="",
            )

            tweets = fetch_list_tweets("list123", 50)

            assert tweets == []


class TestFetchAllLists:
    def test_preprocesses_and_filters_tweets_within_window(self, tmp_path):
        config = {
            "defaults": {"max": 50},
            "sources": [{"id": "list123", "name": "AI Leaders"}],
        }
        until = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        fetch_log = tmp_path / "fetch-errors.jsonl"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=list_envelope(
                    [
                        {
                            "id": "keep-1",
                            "text": "Ship it",
                            "createdAtISO": "2024-01-15T11:30:00+00:00",
                            "author": {"screenName": "alice", "name": "Alice"},
                            "metrics": {
                                "likes": 10,
                                "views": 100,
                                "retweets": 2,
                                "replies": 1,
                                "quotes": 0,
                                "bookmarks": 3,
                            },
                            "urls": ["https://example.com/post"],
                            "media": [{"type": "image", "url": "https://img.example.com/1.png"}],
                        },
                        {
                            "id": "drop-old",
                            "text": "Too old",
                            "createdAtISO": "2024-01-15T08:59:59+00:00",
                            "author": {"screenName": "bob", "name": "Bob"},
                            "metrics": {},
                        },
                    ]
                ),
                stderr="",
            )

            tweets, errors = fetch_all_lists(config, 3, until, fetch_log)

        assert errors == []
        assert len(tweets) == 1
        assert tweets[0] == {
            "id": "keep-1",
            "url": "https://x.com/alice/status/keep-1",
            "author": "@alice (Alice)",
            "time": "2024-01-15T11:30:00+00:00",
            "text": "Ship it",
            "likes": 10,
            "views": 100,
            "retweets": 2,
            "replies": 1,
            "quotes": 0,
            "bookmarks": 3,
            "source": "AI Leaders",
            "links": ["https://example.com/post"],
            "media": [{"type": "image", "url": "https://img.example.com/1.png"}],
        }
        assert fetch_log.read_text(encoding="utf-8") == ""

    def test_excludes_tweets_exactly_at_until_boundary(self, tmp_path):
        config = {
            "defaults": {"max": 50},
            "sources": [{"id": "list123", "name": "AI Leaders"}],
        }
        until = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        fetch_log = tmp_path / "fetch-errors.jsonl"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=list_envelope(
                    [
                        {
                            "id": "keep-before-until",
                            "text": "Keep me",
                            "createdAtISO": "2024-01-15T11:59:59+00:00",
                            "author": {"screenName": "alice", "name": "Alice"},
                            "metrics": {},
                        },
                        {
                            "id": "drop-at-until",
                            "text": "Drop me",
                            "createdAtISO": "2024-01-15T12:00:00+00:00",
                            "author": {"screenName": "bob", "name": "Bob"},
                            "metrics": {},
                        },
                    ]
                ),
                stderr="",
            )

            tweets, errors = fetch_all_lists(config, 3, until, fetch_log)

        assert errors == []
        assert [tweet["id"] for tweet in tweets] == ["keep-before-until"]

    def test_logs_empty_data_error(self, tmp_path):
        config = {
            "defaults": {"max": 50},
            "sources": [{"id": "list123", "name": "AI Leaders"}],
        }
        until = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        fetch_log = tmp_path / "fetch-errors.jsonl"

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=list_envelope([]),
                stderr="",
            )

            tweets, errors = fetch_all_lists(config, 3, until, fetch_log)

        assert tweets == []
        assert len(errors) == 1
        assert errors[0]["meta"]["error_type"] == "empty_data"
        assert errors[0]["meta"]["list_id"] == "list123"
        assert "no tweets returned" in fetch_log.read_text(encoding="utf-8")


class TestDeduplicateTweets:
    def test_removes_duplicates_by_id(self):
        tweets = [
            {"id": "1", "text": "first"},
            {"id": "2", "text": "second"},
            {"id": "1", "text": "duplicate"},
        ]
        result = deduplicate_tweets(tweets)
        assert len(result) == 2
        assert [tweet["id"] for tweet in result] == ["1", "2"]

    def test_empty_list(self):
        assert deduplicate_tweets([]) == []

    def test_empty_id_skipped(self):
        tweets = [{"id": "", "text": "first"}, {"id": "", "text": "second"}]
        result = deduplicate_tweets(tweets)
        assert len(result) == 0

    def test_preserves_order(self):
        tweets = [{"id": "3"}, {"id": "1"}, {"id": "2"}, {"id": "1"}]
        result = deduplicate_tweets(tweets)
        assert [tweet["id"] for tweet in result] == ["3", "1", "2"]


class TestParseIso:
    def test_full_iso8601_with_offset(self):
        dt = parse_iso("2024-01-15T12:00:00+00:00")
        assert dt.year == 2024
        assert dt.month == 1
        assert dt.day == 15
        assert dt.tzinfo is not None

    def test_iso_with_z_suffix(self):
        dt = parse_iso("2024-01-15T12:00:00Z")
        assert dt.tzinfo is not None

    def test_shorthand_offset(self):
        dt = parse_iso("2024-01-15T12:00:00+0000")
        assert dt.tzinfo is not None

    def test_shorthand_negative_offset(self):
        dt = parse_iso("2024-01-15T12:00:00-0800")
        assert dt.tzinfo is not None

    def test_no_timezone_presumed_utc(self):
        dt = parse_iso("2024-01-15T12:00:00")
        assert dt.tzinfo is not None

    def test_whitespace_trimmed(self):
        dt = parse_iso("  2024-01-15T12:00:00Z  ")
        assert dt.year == 2024
