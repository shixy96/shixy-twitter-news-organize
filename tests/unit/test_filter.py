#!/usr/bin/env python3
"""Unit tests for skills/x-news-fetch/scripts/filter.py."""

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys_path_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(sys_path_root / "skills/x-news-fetch/scripts"))

from filter import (
    DEFAULT_MEDIUM,
    DEFAULT_STRONG,
    classify_link,
    filter_posts,
    normalize_domain,
    normalize_external_url,
    normalize_x_url,
    parse_time,
    score,
    signal_tier,
)


class TestNormalizeDomain(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(normalize_domain("Example.COM"), "example.com")

    def test_www_strip(self):
        self.assertEqual(normalize_domain("www.Example.com"), "example.com")

    def test_port_strip(self):
        self.assertEqual(normalize_domain("example.com:8080"), "example.com")

    def test_trailing_dot(self):
        self.assertEqual(normalize_domain("example.com."), "example.com")


class TestNormalizeXUrl(unittest.TestCase):
    def test_valid_url(self):
        result = normalize_x_url("https://twitter.com/user/status/123")
        self.assertEqual(result, "https://x.com/user/status/123")

    def test_x_url(self):
        result = normalize_x_url("https://x.com/user/status/123")
        self.assertEqual(result, "https://x.com/user/status/123")

    def test_non_x_domain(self):
        self.assertIsNone(normalize_x_url("https://example.com/user/status/123"))

    def test_empty(self):
        self.assertIsNone(normalize_x_url(""))

    def test_no_path(self):
        self.assertIsNone(normalize_x_url("https://x.com/"))

    def test_trailing_slash(self):
        result = normalize_x_url("https://x.com/user/status/123/")
        self.assertEqual(result, "https://x.com/user/status/123")


class TestNormalizeExternalUrl(unittest.TestCase):
    def test_basic(self):
        result = normalize_external_url("https://example.com/path")
        self.assertEqual(result, "https://example.com/path")

    def test_github(self):
        result = normalize_external_url("https://github.com/user/repo")
        self.assertEqual(result, "https://github.com/user/repo")

    def test_query_string(self):
        result = normalize_external_url("https://example.com/path?foo=bar")
        self.assertEqual(result, "https://example.com/path?foo=bar")

    def test_fragment(self):
        result = normalize_external_url("https://example.com/path#section")
        self.assertEqual(result, "https://example.com/path#section")

    def test_empty(self):
        self.assertIsNone(normalize_external_url(""))

    def test_no_scheme(self):
        self.assertIsNone(normalize_external_url("example.com/path"))


class TestParseTime(unittest.TestCase):
    def test_iso_with_offset(self):
        result = parse_time("2026-04-06T10:00:00+00:00")
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.year, 2026)

    def test_iso_z_suffix(self):
        result = parse_time("2026-04-06T10:00:00Z")
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.year, 2026)

    def test_iso_without_tz(self):
        result = parse_time("2026-04-06T10:00:00")
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.tzinfo, timezone.utc)

    def test_short_offset(self):
        result = parse_time("2026-04-06T10:00:00+0800")
        self.assertIsInstance(result, datetime)

    def test_empty(self):
        self.assertIsNone(parse_time(""))

    def test_invalid(self):
        self.assertIsNone(parse_time("not a date"))


class TestScore(unittest.TestCase):
    def test_basic(self):
        p = {"likes": 100, "bookmarks": 10, "quotes": 5}
        self.assertEqual(score(p), 100 + 10 * 2 + 5 * 3)

    def test_missing_fields(self):
        p = {}
        self.assertEqual(score(p), 0)

    def test_zeros(self):
        p = {"likes": 0, "bookmarks": 0, "quotes": 0}
        self.assertEqual(score(p), 0)


class TestSignalTier(unittest.TestCase):
    def test_strong_signal(self):
        result = signal_tier(
            likes=300, bookmarks=100, views=10000, strong=DEFAULT_STRONG, medium=DEFAULT_MEDIUM
        )
        self.assertEqual(result, "strong")

    def test_medium_signal(self):
        result = signal_tier(
            likes=100, bookmarks=50, views=10000, strong=DEFAULT_STRONG, medium=DEFAULT_MEDIUM
        )
        self.assertEqual(result, "medium")

    def test_no_signal(self):
        result = signal_tier(
            likes=10, bookmarks=5, views=1000, strong=DEFAULT_STRONG, medium=DEFAULT_MEDIUM
        )
        self.assertIsNone(result)

    def test_interaction_rate_strong(self):
        # 200 likes / 10000 views = 0.02 >= 0.015
        result = signal_tier(
            likes=200, bookmarks=10, views=10000, strong=DEFAULT_STRONG, medium=DEFAULT_MEDIUM
        )
        self.assertEqual(result, "strong")


class TestClassifyLink(unittest.TestCase):
    def test_github(self):
        result = classify_link("https://github.com/user/repo")
        self.assertEqual(result, ("github", 100))

    def test_arxiv(self):
        result = classify_link("https://arxiv.org/abs/1234.5678")
        self.assertEqual(result, ("arxiv", 95))

    def test_huggingface(self):
        result = classify_link("https://huggingface.co/models/test")
        self.assertEqual(result, ("huggingface", 90))

    def test_official_domain(self):
        result = classify_link("https://openai.com/blog/test")
        self.assertEqual(result, ("official", 88))

    def test_x_twitter(self):
        self.assertIsNone(classify_link("https://x.com/user/status/123"))

    def test_external(self):
        result = classify_link("https://example.com/other")
        self.assertEqual(result, ("external", 10))


class TestFilterPosts(unittest.TestCase):
    def setUp(self):
        fixture_path = Path(__file__).resolve().parent.parent / "fixtures/filter/raw_tweets.json"
        with open(fixture_path, encoding="utf-8") as f:
            self.raw_tweets = json.load(f)
        self.now = datetime(2026, 4, 6, 12, 0, 0, tzinfo=timezone.utc)

    def test_filter_posts_basic(self):
        result = filter_posts(self.raw_tweets, now=self.now)
        self.assertIn("stats", result)
        self.assertIn("strong", result)
        self.assertIn("medium", result)
        self.assertIn("backfill", result)

    def test_stats_fields(self):
        result = filter_posts(self.raw_tweets, now=self.now)
        stats = result["stats"]
        self.assertIn("total_raw", stats)
        self.assertIn("unique", stats)
        self.assertIn("within_window", stats)

    def test_no_duplicates(self):
        result = filter_posts(self.raw_tweets, now=self.now)
        all_ids = []
        for bucket in [result["strong"], result["medium"], result["backfill"]]:
            for item in bucket:
                all_ids.append(item["id"])
        self.assertEqual(len(all_ids), len(set(all_ids)))

    def test_author_cap(self):
        # Raw tweets should be limited to 2 per author per bucket
        result = filter_posts(self.raw_tweets, now=self.now)
        for bucket_name, bucket in [
            ("strong", result["strong"]),
            ("medium", result["medium"]),
            ("backfill", result["backfill"]),
        ]:
            author_counts = {}
            for item in bucket:
                author = item.get("author", "")
                author_counts[author] = author_counts.get(author, 0) + 1
                self.assertLessEqual(
                    author_counts[author], 2, f"Author {author} exceeds cap in {bucket_name}"
                )


if __name__ == "__main__":
    unittest.main()
