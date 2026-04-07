#!/usr/bin/env python3
"""Unit tests for skills/x-news-fetch/scripts/fetch.py."""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys_path_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(sys_path_root / "skills/x-news-fetch/scripts"))

from fetch import (
    deduplicate_and_sort,
    format_author,
    metric_value,
    parse_iso,
    preprocess_tweet,
    validate_raw,
)


class TestParseIso(unittest.TestCase):
    def test_iso_with_offset(self):
        result = parse_iso("2026-04-06T10:00:00+00:00")
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.year, 2026)
        self.assertEqual(result.month, 4)
        self.assertEqual(result.day, 6)

    def test_iso_z_suffix(self):
        result = parse_iso("2026-04-06T10:00:00Z")
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.tzinfo, timezone.utc)

    def test_iso_no_tz(self):
        result = parse_iso("2026-04-06T10:00:00")
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.tzinfo, timezone.utc)

    def test_short_offset(self):
        result = parse_iso("2026-04-06T10:00:00+0800")
        self.assertIsInstance(result, datetime)

    def test_whitespace(self):
        result = parse_iso("  2026-04-06T10:00:00+00:00  ")
        self.assertIsInstance(result, datetime)

    def test_invalid(self):
        with self.assertRaises(ValueError):
            parse_iso("not a date")


class TestFormatAuthor(unittest.TestCase):
    def test_both_fields(self):
        author = {"screenName": "user1", "name": "Alice"}
        result = format_author(author)
        self.assertEqual(result, "@user1 (Alice)")

    def test_screen_name_only(self):
        author = {"screenName": "user1"}
        result = format_author(author)
        self.assertEqual(result, "@user1")

    def test_name_only(self):
        author = {"name": "Alice"}
        result = format_author(author)
        self.assertEqual(result, "Alice")

    def test_empty(self):
        result = format_author({})
        self.assertEqual(result, "")


class TestMetricValue(unittest.TestCase):
    def test_valid_int(self):
        self.assertEqual(metric_value({"likes": 100}, "likes"), 100)

    def test_default_zero(self):
        self.assertEqual(metric_value({}, "likes"), 0)

    def test_non_int(self):
        self.assertEqual(metric_value({"likes": "bad"}, "likes"), 0)


class TestPreprocessTweet(unittest.TestCase):
    def test_basic(self):
        raw = {
            "id": "123",
            "author": {"screenName": "user", "name": "User"},
            "createdAtISO": "2026-04-06T10:00:00Z",
            "text": "Hello world",
            "metrics": {"likes": 10, "views": 100},
        }
        result = preprocess_tweet(raw, "TestSource")
        self.assertEqual(result["id"], "123")
        self.assertEqual(result["author"], "@user (User)")
        self.assertEqual(result["source"], "TestSource")
        self.assertEqual(result["likes"], 10)
        self.assertEqual(result["views"], 100)

    def test_retweet(self):
        raw = {
            "id": "123",
            "isRetweet": True,
            "retweetedBy": "other_user",
            "author": {"screenName": "user", "name": "User"},
            "text": "RT text",
            "metrics": {},
        }
        result = preprocess_tweet(raw, "Test")
        self.assertTrue(result.get("is_retweet"))
        self.assertEqual(result.get("retweeted_by"), "@other_user")

    def test_reply_detection(self):
        raw = {
            "id": "123",
            "author": {"screenName": "user"},
            "text": "@other_user reply text",
            "metrics": {},
        }
        result = preprocess_tweet(raw, "Test")
        self.assertTrue(result.get("likely_reply"))

    def test_quoted_tweet(self):
        raw = {
            "id": "123",
            "author": {"screenName": "user"},
            "text": "quote text",
            "metrics": {},
            "quotedTweet": {
                "id": "456",
                "author": {"screenName": "other", "name": "Other"},
                "text": "quoted text",
            },
        }
        result = preprocess_tweet(raw, "Test")
        self.assertIn("quoted", result)

    def test_links_and_media(self):
        raw = {
            "id": "123",
            "author": {"screenName": "user"},
            "text": "text",
            "metrics": {},
            "urls": ["https://example.com"],
            "media": ["https://example.com/img.jpg"],
        }
        result = preprocess_tweet(raw, "Test")
        self.assertEqual(result["links"], ["https://example.com"])
        self.assertEqual(result["media"], ["https://example.com/img.jpg"])


class TestDeduplicateAndSort(unittest.TestCase):
    def test_deduplication(self):
        tweets = [
            {"id": "1", "time": "2026-04-06T10:00:00Z"},
            {"id": "2", "time": "2026-04-06T11:00:00Z"},
            {"id": "1", "time": "2026-04-06T10:00:00Z"},
        ]
        result = deduplicate_and_sort(tweets)
        self.assertEqual(len(result), 2)

    def test_sort_newest_first(self):
        tweets = [
            {"id": "1", "time": "2026-04-06T08:00:00Z"},
            {"id": "2", "time": "2026-04-06T12:00:00Z"},
            {"id": "3", "time": "2026-04-06T10:00:00Z"},
        ]
        result = deduplicate_and_sort(tweets)
        self.assertEqual(result[0]["id"], "2")
        self.assertEqual(result[1]["id"], "3")
        self.assertEqual(result[2]["id"], "1")


class TestValidateRaw(unittest.TestCase):
    def test_valid_tweets(self):
        tweets = [
            {
                "id": "1",
                "url": "https://x.com/1",
                "author": "a",
                "text": "t",
                "time": "2026-04-06T10:00:00Z",
            },
            {
                "id": "2",
                "url": "https://x.com/2",
                "author": "b",
                "text": "t",
                "time": "2026-04-06T10:00:00Z",
            },
        ]
        self.assertTrue(validate_raw(tweets))

    def test_empty_list(self):
        self.assertFalse(validate_raw([]))

    def test_missing_field(self):
        tweets = [
            {"id": "1", "url": "https://x.com/1", "author": "a", "text": "t"},
        ]
        self.assertFalse(validate_raw(tweets))

    def test_only_checks_first_five(self):
        """validate_raw only checks first 5 tweets, so missing fields beyond index 4 are ok."""
        tweets = [
            {
                "id": str(i),
                "url": f"https://x.com/{i}",
                "author": "a",
                "text": "t",
                "time": "2026-04-06T10:00:00Z",
            }
            for i in range(10)
        ]
        # Remove 'author' from items 5-9 only, so first 5 still pass
        for t in tweets[5:]:
            del t["author"]
        self.assertTrue(validate_raw(tweets))


if __name__ == "__main__":
    unittest.main()
