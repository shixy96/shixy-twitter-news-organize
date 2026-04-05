"""Tests for filter.py - engagement filtering logic."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

SCRIPTS_PATH = (
    Path(__file__).parent.parent.parent.parent / "skills" / "x-news-data-pipeline" / "scripts"
)
sys.path.insert(0, str(SCRIPTS_PATH))

from filter import (
    signal_tier_from_metrics,
    is_noise,
    is_self_promo,
    classify_window,
    filter_posts,
)


class TestSignalTierFromMetrics:
    """Test engagement signal tier classification."""

    def test_strong_all_conditions_met(self):
        """Strong: 2+ conditions met."""
        result = signal_tier_from_metrics(
            likes=300,
            bookmarks=100,
            views=10000,
            strong_thresholds={
                "conditions": 2,
                "likes": 200,
                "bookmarks": 80,
                "interaction_rate": 0.015,
            },
            medium_thresholds={"conditions": 1, "likes": 50, "bookmarks": 20},
        )
        assert result == "strong"

    def test_strong_interaction_rate_only(self):
        """Strong: likes threshold + IR threshold = 2 conditions met."""
        result = signal_tier_from_metrics(
            likes=200,
            bookmarks=79,
            views=10000,
            strong_thresholds={
                "conditions": 2,
                "likes": 200,
                "bookmarks": 80,
                "interaction_rate": 0.015,
            },
            medium_thresholds={"conditions": 1, "likes": 50, "bookmarks": 20},
        )
        assert result == "strong"  # likes>=200 (1) + IR>=0.015 (1) = 2 conditions

    def test_medium_sufficient(self):
        """Medium: 1 condition met."""
        result = signal_tier_from_metrics(
            likes=100,
            bookmarks=30,
            views=1000,
            strong_thresholds={
                "conditions": 2,
                "likes": 200,
                "bookmarks": 80,
                "interaction_rate": 0.015,
            },
            medium_thresholds={"conditions": 1, "likes": 50, "bookmarks": 20},
        )
        assert result == "medium"

    def test_below_threshold(self):
        """No tier: below all thresholds."""
        result = signal_tier_from_metrics(
            likes=10,
            bookmarks=2,
            views=100,
            strong_thresholds={
                "conditions": 2,
                "likes": 200,
                "bookmarks": 80,
                "interaction_rate": 0.015,
            },
            medium_thresholds={"conditions": 1, "likes": 50, "bookmarks": 20},
        )
        assert result is None

    def test_zero_views(self):
        """Zero views should not crash, IR is 0."""
        result = signal_tier_from_metrics(
            likes=0,
            bookmarks=0,
            views=0,
            strong_thresholds={
                "conditions": 2,
                "likes": 200,
                "bookmarks": 80,
                "interaction_rate": 0.015,
            },
            medium_thresholds={"conditions": 1, "likes": 50, "bookmarks": 20},
        )
        assert result is None


class TestIsNoise:
    def test_below_noise_threshold(self):
        assert is_noise({"likes": 5, "bookmarks": 2}) is True

    def test_above_noise_threshold(self):
        assert is_noise({"likes": 20, "bookmarks": 10}) is False

    def test_missing_fields(self):
        assert is_noise({}) is True


class TestIsSelfPromo:
    def test_self_promo_low_engagement(self):
        """Self promo with low engagement is filtered."""
        result = is_self_promo({"text": "We are hiring engineers!", "likes": 50, "bookmarks": 20})
        assert result is True

    def test_self_promo_high_engagement(self):
        """Self promo with high engagement is NOT filtered (it's legitimate)."""
        result = is_self_promo({"text": "We are hiring engineers!", "likes": 500, "bookmarks": 100})
        assert result is False

    def test_normal_post(self):
        """Normal post is not self promo."""
        result = is_self_promo({"text": "Great AI research paper!", "likes": 100, "bookmarks": 50})
        assert result is False


class TestClassifyWindow:
    def test_future(self):
        """Future dates are fresh."""
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        result = classify_window(
            future, datetime.now(timezone.utc), fresh_hours=24, backfill_hours=48
        )
        assert result == "fresh"

    def test_within_fresh(self):
        """Within fresh window."""
        recent = datetime.now(timezone.utc) - timedelta(hours=12)
        result = classify_window(
            recent, datetime.now(timezone.utc), fresh_hours=24, backfill_hours=48
        )
        assert result == "fresh"

    def test_within_backfill(self):
        """Within backfill window."""
        older = datetime.now(timezone.utc) - timedelta(hours=36)
        result = classify_window(
            older, datetime.now(timezone.utc), fresh_hours=24, backfill_hours=48
        )
        assert result == "backfill"

    def test_outside_window(self):
        """Outside backfill window."""
        old = datetime.now(timezone.utc) - timedelta(hours=72)
        result = classify_window(old, datetime.now(timezone.utc), fresh_hours=24, backfill_hours=48)
        assert result is None


class TestFilterPosts:
    def test_empty_input(self, now):
        result = filter_posts([], now=now)
        assert result["stats"]["total_raw"] == 0
        assert result["strong"] == []
        assert result["medium"] == []
        assert result["backfill"] == []

    def test_noise_filtered(self, now):
        """Low engagement posts should be filtered."""
        tweets = [
            {
                "id": "1",
                "url": "https://x.com/user/status/1",
                "author": "user",
                "text": "Test",
                "time": (now - timedelta(hours=1)).isoformat(),
                "likes": 5,
                "bookmarks": 2,
                "views": 100,
            }
        ]
        result = filter_posts(tweets, now=now)
        assert result["stats"]["skipped"] >= 1

    def test_self_promo_filtered(self, now):
        """Self promo posts should be filtered."""
        tweets = [
            {
                "id": "1",
                "url": "https://x.com/user/status/1",
                "author": "user",
                "text": "We are hiring engineers to join our team!",
                "time": (now - timedelta(hours=1)).isoformat(),
                "likes": 50,
                "bookmarks": 20,
                "views": 1000,
            }
        ]
        result = filter_posts(tweets, now=now)
        assert result["stats"]["skipped"] >= 1

    def test_output_structure(self, now):
        tweets = [
            {
                "id": "1",
                "url": "https://x.com/user/status/1",
                "author": "user",
                "text": "AI breakthrough",
                "time": (now - timedelta(hours=1)).isoformat(),
                "likes": 300,
                "bookmarks": 100,
                "views": 10000,
            }
        ]
        result = filter_posts(tweets, now=now)
        assert "stats" in result
        assert "strong" in result
        assert "medium" in result
        assert "backfill" in result
        assert "skipped_breakdown" in result["stats"]
