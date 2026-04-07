#!/usr/bin/env python3
"""
Fetch tweets from X Lists via twitter CLI.

Usage:
    python3 fetch.py --config <path> --hours <N> --until <iso8601> [--output <path>]

Exit codes:
    0 - Success (raw.json written and validated)
    1 - Fetch failed or validation failed
    2 - Missing required arguments
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def parse_iso(value: str) -> datetime:
    """Parse ISO 8601 datetime string."""
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    if len(normalized) >= 5 and normalized[-5] in "+-" and normalized[-3] != ":":
        normalized = f"{normalized[:-2]}:{normalized[-2:]}"
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def run_twitter_json(cmd: list[str], *, timeout: int, label: str) -> list[dict]:
    """Run twitter-cli and return the envelope's data array."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        print(f"{label}: 'twitter' command not found", file=sys.stderr)
        return []
    except subprocess.TimeoutExpired:
        print(f"{label}: timed out after {timeout}s", file=sys.stderr)
        return []

    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit code {result.returncode}"
        print(f"{label}: {detail}", file=sys.stderr)
        return []

    if not result.stdout.strip():
        print(f"{label}: empty response", file=sys.stderr)
        return []

    try:
        envelope = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"{label}: invalid JSON ({e})", file=sys.stderr)
        return []

    if not isinstance(envelope, dict) or not envelope.get("ok", False):
        msg = (
            envelope.get("error", {}).get("message", "unknown")
            if isinstance(envelope, dict)
            else "not a JSON object"
        )
        print(f"{label}: API error ({msg})", file=sys.stderr)
        return []

    data = envelope.get("data", [])
    if not isinstance(data, list):
        print(f"{label}: 'data' is not an array", file=sys.stderr)
        return []

    return [item for item in data if isinstance(item, dict)]


def format_author(author: dict) -> str:
    screen_name = author.get("screenName", "")
    name = author.get("name", "")
    if screen_name and name:
        return f"@{screen_name} ({name})"
    return f"@{screen_name}" if screen_name else name


def metric_value(metrics: dict, key: str) -> int:
    value = metrics.get(key, 0)
    return value if isinstance(value, int) else 0


def preprocess_tweet(raw: dict, source_name: str) -> dict:
    """Flatten twitter-cli raw payload into the raw.json schema."""
    author = raw.get("author") if isinstance(raw.get("author"), dict) else {}
    screen_name = author.get("screenName", "")
    tweet_id = raw.get("id", "")
    metrics = raw.get("metrics") if isinstance(raw.get("metrics"), dict) else {}
    quoted = raw.get("quotedTweet") if isinstance(raw.get("quotedTweet"), dict) else None
    urls = raw.get("urls") if isinstance(raw.get("urls"), list) else []
    media = raw.get("media") if isinstance(raw.get("media"), list) else []
    text = raw.get("text", "")

    tweet = {
        "id": tweet_id,
        "url": f"https://x.com/{screen_name}/status/{tweet_id}"
        if screen_name and tweet_id
        else raw.get("url", ""),
        "author": format_author(author),
        "time": raw.get("createdAtISO", raw.get("createdAt", "")),
        "text": text,
        "likes": metric_value(metrics, "likes"),
        "views": metric_value(metrics, "views"),
        "retweets": metric_value(metrics, "retweets"),
        "replies": metric_value(metrics, "replies"),
        "quotes": metric_value(metrics, "quotes"),
        "bookmarks": metric_value(metrics, "bookmarks"),
        "source": source_name,
    }

    if raw.get("isRetweet"):
        tweet["is_retweet"] = True
    if raw.get("retweetedBy"):
        tweet["retweeted_by"] = f"@{raw['retweetedBy']}"
    if isinstance(text, str) and re.match(r"^@\w", text):
        tweet["likely_reply"] = True
    if quoted:
        qa = quoted.get("author") if isinstance(quoted.get("author"), dict) else {}
        qs = qa.get("screenName", "")
        qi = quoted.get("id", "")
        qt = quoted.get("text", "")
        if qs or qt:
            tweet["quoted"] = f"@{qs}: {qt}".rstrip(": ")
        if qi:
            tweet["quoted_id"] = qi
        if qs and qi:
            tweet["quoted_url"] = f"https://x.com/{qs}/status/{qi}"
        if qa:
            tweet["quoted_author"] = format_author(qa)
        if qt:
            tweet["quoted_text"] = qt
    if urls:
        tweet["links"] = [u for u in urls if isinstance(u, str)]
    if media:
        tweet["media"] = media

    return tweet


def fetch_all_lists(config: dict, hours: int, until: datetime) -> list[dict]:
    """Fetch, preprocess, and time-filter tweets from every configured list."""
    defaults = config.get("defaults", {})
    max_default = defaults.get("max", 50)
    sources = config.get("sources", [])
    if not sources:
        print("Warning: no sources in config", file=sys.stderr)
        return []

    all_tweets: list[dict] = []
    window_start = until - timedelta(hours=hours)
    errors = 0

    for source in sources:
        list_id = source.get("id")
        name = source.get("name", "unknown")
        max_tweets = source.get("max", max_default)
        if not list_id:
            print(f"Warning: source '{name}' missing list id", file=sys.stderr)
            errors += 1
            continue

        raw_tweets = run_twitter_json(
            ["twitter", "list", list_id, "--json", "--full-text", "--max", str(max_tweets)],
            timeout=120,
            label=f"[fetch:{name}]",
        )
        if not raw_tweets:
            errors += 1
            continue

        for raw_tweet in raw_tweets:
            tweet = preprocess_tweet(raw_tweet, name)
            time_str = tweet.get("time", "")
            if not time_str:
                continue
            try:
                tweet_time = parse_iso(time_str)
            except (TypeError, ValueError):
                continue
            if window_start <= tweet_time < until:
                all_tweets.append(tweet)

    print(
        f"[fetch] {len(all_tweets)} tweets from {len(sources)} sources, {errors} errors",
        file=sys.stderr,
    )
    return all_tweets


def _engagement_score(t: dict) -> int:
    """Compute engagement score for deduplication quality comparison."""
    return t.get("likes", 0) + t.get("bookmarks", 0) * 2 + t.get("quotes", 0) * 3


def deduplicate_and_sort(tweets: list[dict]) -> list[dict]:
    """Deduplicate by id and sort newest-first, keeping highest-engagement copy."""
    by_id: dict[str, dict] = {}
    for t in tweets:
        tid = t.get("id", "")
        if not tid:
            continue
        if tid not in by_id or _engagement_score(t) > _engagement_score(by_id[tid]):
            by_id[tid] = t

    def sort_key(t: dict) -> datetime:
        try:
            return parse_iso(t.get("time", ""))
        except (TypeError, ValueError):
            return datetime.min.replace(tzinfo=timezone.utc)

    return sorted(by_id.values(), key=sort_key, reverse=True)


def validate_raw(tweets: list[dict]) -> bool:
    """Quick validation: non-empty array of objects with required fields."""
    if not tweets:
        print("Error: no tweets to validate", file=sys.stderr)
        return False
    required = {"id", "url", "author", "text", "time"}
    for i, t in enumerate(tweets[:5]):
        missing = required - set(t.keys())
        if missing:
            print(f"Error: tweet[{i}] missing fields: {missing}", file=sys.stderr)
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch tweets from X Lists")
    parser.add_argument("--config", type=Path, required=True, help="SOURCE_CONFIG JSON path")
    parser.add_argument("--hours", type=int, required=True, help="Fetch window in hours")
    parser.add_argument("--until", type=str, required=True, help="Cutoff time ISO 8601")
    parser.add_argument("--output", type=Path, default=None, help="Output path (default: stdout)")
    args = parser.parse_args()

    try:
        with open(args.config, encoding="utf-8") as f:
            config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error: invalid config: {e}", file=sys.stderr)
        return 2

    try:
        until = parse_iso(args.until)
    except (ValueError, TypeError) as e:
        print(f"Error: invalid --until time: {e}", file=sys.stderr)
        return 2

    tweets = fetch_all_lists(config, args.hours, until)
    if not tweets:
        print("Error: no tweets fetched", file=sys.stderr)
        return 1

    tweets = deduplicate_and_sort(tweets)
    if not validate_raw(tweets):
        return 1

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(tweets, f, ensure_ascii=False)
            f.write("\n")
    else:
        json.dump(tweets, sys.stdout, ensure_ascii=False)
        print()

    print(f"RAW_JSON_OK ({len(tweets)} tweets)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
