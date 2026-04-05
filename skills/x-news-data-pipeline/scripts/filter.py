#!/usr/bin/env python3
"""
x-news-filter: Pre-filter X list raw JSON by engagement signal strength.

Reads thresholds from SOURCE_CONFIG if provided, falls back to hardcoded defaults.

Usage:
    python3 filter.py <raw_json_file> [--config SOURCE_CONFIG] [--top N]
    python3 filter.py <raw_json_file> --fresh-hours 24 --backfill-hours 48

Output (stdout): JSON grouped into fresh strong/medium plus backfill candidates.
"""

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT_DIR = Path(__file__).resolve().parents[3]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from x_news_shared import append_run_log, normalize_domain, normalize_external_url, normalize_x_url


# Hardcoded defaults (used when SOURCE_CONFIG is not provided)
DEFAULT_STRONG_THRESHOLDS = {
    "conditions": 2,
    "likes": 200,
    "bookmarks": 80,
    "interaction_rate": 0.015,
}
DEFAULT_MEDIUM_THRESHOLDS = {
    "conditions": 1,
    "likes": 50,
    "bookmarks": 20,
}

TIER_RANK = {None: 0, "medium": 1, "strong": 2}
HIGH_VALUE_LINK_HOSTS = {
    "github.com": ("github", 100),
    "gist.github.com": ("github", 100),
    "raw.githubusercontent.com": ("github", 100),
    "arxiv.org": ("arxiv", 95),
    "huggingface.co": ("huggingface", 90),
    "hf.co": ("huggingface", 90),
    "paperswithcode.com": ("paper", 85),
    "openreview.net": ("paper", 85),
}
OFFICIAL_DOMAIN_SUFFIXES = {
    "openai.com",
    "anthropic.com",
    "claude.com",
    "ai.google.dev",
    "deepmind.google",
    "research.google",
    "blog.google",
    "googleblog.com",
    "ai.meta.com",
    "meta.com",
    "about.fb.com",
    "engineering.fb.com",
    "github.blog",
    "figma.com",
    "mistral.ai",
    "cohere.com",
    "replicate.com",
    "together.ai",
    "fireworks.ai",
    "groq.com",
    "nvidia.com",
    "developer.nvidia.com",
    "research.nvidia.com",
    "vercel.com",
}
OFFICIAL_HOST_HINTS = ("docs.", "blog.", "changelog.")
OFFICIAL_PATH_HINTS = {
    "docs",
    "doc",
    "blog",
    "changelog",
    "release",
    "releases",
    "announcement",
    "announcements",
    "news",
}


def load_source_config(config_path: str | None) -> dict:
    """Load SOURCE_CONFIG if provided, returns empty dict if not found or not given."""
    if not config_path:
        return {}
    try:
        with open(config_path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def get_signal_thresholds(config: dict) -> tuple[dict, dict]:
    """Extract signal thresholds from config, falling back to defaults."""
    thresholds = config.get("signal_thresholds", {})
    strong = thresholds.get("strong", DEFAULT_STRONG_THRESHOLDS)
    medium = thresholds.get("medium", DEFAULT_MEDIUM_THRESHOLDS)
    return strong, medium


def score(post: dict) -> int:
    return post.get("likes", 0) + post.get("bookmarks", 0) * 2 + post.get("quotes", 0) * 3


def interaction_rate(post: dict) -> float:
    views = post.get("views", 0)
    return post.get("likes", 0) / views if views > 0 else 0.0


def is_noise(post: dict) -> bool:
    return post.get("likes", 0) < 10 and post.get("bookmarks", 0) < 5


def is_self_promo(post: dict) -> bool:
    text = post.get("text", "").lower()
    promo_kws = [
        "we are hiring",
        "join our team",
        "job opening",
        "now hiring",
        "amzn.to",
    ]
    if any(kw in text for kw in promo_kws):
        return post.get("likes", 0) < 100 and post.get("bookmarks", 0) < 50
    return False


def signal_tier_from_metrics(
    likes: int, bookmarks: int, views: int, strong_thresholds: dict, medium_thresholds: dict
) -> str | None:
    """Determine signal tier based on configurable thresholds.

    Args:
        likes: Number of likes
        bookmarks: Number of bookmarks
        views: Number of views
        strong_thresholds: Dict with likes, bookmarks, interaction_rate thresholds
        medium_thresholds: Dict with likes, bookmarks thresholds

    Returns:
        "strong", "medium", or None
    """
    ir = likes / views if views > 0 else 0.0
    strong_conditions = 0
    if likes >= strong_thresholds.get("likes", 200):
        strong_conditions += 1
    if bookmarks >= strong_thresholds.get("bookmarks", 80):
        strong_conditions += 1
    if ir >= strong_thresholds.get("interaction_rate", 0.015):
        strong_conditions += 1

    required_strong_conditions = strong_thresholds.get("conditions", 2)
    if strong_conditions >= required_strong_conditions:
        return "strong"

    medium_conditions = 0
    if likes >= medium_thresholds.get("likes", 50):
        medium_conditions += 1
    if bookmarks >= medium_thresholds.get("bookmarks", 20):
        medium_conditions += 1

    required_medium_conditions = medium_thresholds.get("conditions", 1)
    if medium_conditions >= required_medium_conditions:
        return "medium"

    return None


def signal_tier_with_config(
    post: dict, strong_thresholds: dict, medium_thresholds: dict
) -> str | None:
    return signal_tier_from_metrics(
        post.get("likes", 0),
        post.get("bookmarks", 0),
        post.get("views", 0),
        strong_thresholds,
        medium_thresholds,
    )


def parse_cli_time(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if len(normalized) >= 5 and normalized[-5] in "+-" and normalized[-3] != ":":
        normalized = f"{normalized[:-2]}:{normalized[-2:]}"
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def parse_tweet_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return parse_cli_time(value)
    except ValueError:
        return None


def domain_matches_suffix(domain: str, suffix: str) -> bool:
    return domain == suffix or domain.endswith(f".{suffix}")


def is_allowlisted_official_domain(domain: str) -> bool:
    return any(domain_matches_suffix(domain, suffix) for suffix in OFFICIAL_DOMAIN_SUFFIXES)


def classify_external_link(url: str) -> tuple[str, int] | None:
    parsed = urlparse(url)
    domain = normalize_domain(parsed.netloc)
    if domain in {"x.com", "twitter.com"}:
        return None

    if domain in HIGH_VALUE_LINK_HOSTS:
        return HIGH_VALUE_LINK_HOSTS[domain]

    if is_allowlisted_official_domain(domain):
        return ("official", 88)

    path_tokens = {token for token in re.split(r"[/_-]+", parsed.path.lower()) if token}
    if domain.startswith(OFFICIAL_HOST_HINTS) or path_tokens & OFFICIAL_PATH_HINTS:
        return ("official", 80)

    return ("external", 10)


def collect_group_links(members: list[dict]) -> tuple[list[dict], list[dict]]:
    by_url: dict[str, dict] = {}

    for post in members:
        for raw_url in post.get("links") or []:
            normalized = normalize_external_url(raw_url)
            if not normalized:
                continue

            classification = classify_external_link(normalized)
            if classification is None:
                continue

            kind, priority = classification
            domain = normalize_domain(urlparse(normalized).netloc)
            entry = by_url.setdefault(
                normalized,
                {
                    "url": normalized,
                    "domain": domain,
                    "kind": kind,
                    "mentions": 0,
                    "_priority": priority,
                    "_best_score": 0,
                },
            )
            entry["mentions"] += 1
            entry["_priority"] = max(entry["_priority"], priority)
            entry["_best_score"] = max(entry["_best_score"], post["_base_score"])
            if entry["kind"] == "external" and kind != "external":
                entry["kind"] = kind

    ranked = sorted(
        by_url.values(),
        key=lambda item: (-item["_priority"], -item["mentions"], -item["_best_score"], item["url"]),
    )
    external_links = [
        {
            "url": item["url"],
            "domain": item["domain"],
            "kind": item["kind"],
            "mentions": item["mentions"],
        }
        for item in ranked[:8]
    ]
    strong_links = [item for item in external_links if item["kind"] != "external"][:5]
    return external_links, strong_links


def classify_window(
    tweet_time: datetime, now: datetime, fresh_hours: float, backfill_hours: float
) -> str | None:
    age = now - tweet_time
    if age < timedelta(0):
        return "fresh"
    if age < timedelta(hours=fresh_hours):
        return "fresh"
    if age < timedelta(hours=backfill_hours):
        return "backfill"
    return None


def canonical_key(post: dict) -> str:
    return post.get("source_id") or post.get("quoted_id") or post["id"]


def canonical_url(post: dict) -> str:
    return post.get("source_url") or post.get("quoted_url") or post["url"]


def canonical_author(post: dict) -> str:
    return post.get("source_author") or post.get("quoted_author") or post["author"]


def canonical_text(post: dict) -> str:
    return post.get("source_text") or post.get("quoted_text") or post["text"]


def author_thread_urls(post: dict) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    screen_name = ""
    parsed = urlparse(post.get("url", ""))
    path_parts = [part for part in parsed.path.split("/") if part]
    if len(path_parts) >= 3:
        screen_name = path_parts[0]

    for reply_id in post.get("thread_reply_ids") or []:
        if not screen_name or not reply_id:
            continue
        url = normalize_x_url(f"https://x.com/{screen_name}/status/{reply_id}")
        if url and url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def append_unique(items: list[str], seen: set[str], values: list[str]) -> None:
    for value in values:
        if value and value not in seen:
            seen.add(value)
            items.append(value)


def representative_sort_key(post: dict, key: str) -> tuple:
    return (
        1 if post["id"] == key else 0,
        TIER_RANK[post["_base_signal"]],
        post["_base_score"],
        post.get("bookmarks", 0),
        post.get("likes", 0),
    )


def build_candidate(
    post: dict,
    now: datetime,
    fresh_hours: float,
    backfill_hours: float,
    strong_thresholds: dict,
    medium_thresholds: dict,
) -> dict | None:
    tweet_time = parse_tweet_time(post.get("time", ""))
    if tweet_time is None:
        return None

    window = classify_window(tweet_time, now, fresh_hours, backfill_hours)
    if window is None:
        return None

    candidate = dict(post)
    candidate["_tweet_time"] = tweet_time
    candidate["_window"] = window
    candidate["_canonical_key"] = canonical_key(post)
    candidate["_base_signal"] = signal_tier_with_config(post, strong_thresholds, medium_thresholds)
    candidate["_base_score"] = score(post)
    candidate["_interaction_rate"] = round(interaction_rate(post), 4)
    return candidate


def group_candidates(
    posts: list[dict], strong_thresholds: dict, medium_thresholds: dict
) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for post in posts:
        groups[post["_canonical_key"]].append(post)

    grouped: list[dict] = []
    for key, members in groups.items():
        representative = max(members, key=lambda post: representative_sort_key(post, key))

        source_posts = [post for post in members if post["id"] == key]
        if source_posts:
            canonical = max(source_posts, key=lambda post: representative_sort_key(post, key))
            anchor_time = canonical["_tweet_time"]
        else:
            canonical = representative
            anchor_time = max(post["_tweet_time"] for post in members)

        agg_likes = sum(post.get("likes", 0) for post in members)
        agg_views = sum(post.get("views", 0) for post in members)
        agg_bookmarks = sum(post.get("bookmarks", 0) for post in members)
        agg_quotes = sum(post.get("quotes", 0) for post in members)
        agg_score = sum(post["_base_score"] for post in members)
        agg_signal = signal_tier_from_metrics(
            agg_likes, agg_bookmarks, agg_views, strong_thresholds, medium_thresholds
        )
        max_base_signal = max(
            (post["_base_signal"] for post in members),
            key=lambda tier: TIER_RANK[tier],
        )
        final_signal = max((agg_signal, max_base_signal), key=lambda tier: TIER_RANK[tier])

        item = dict(representative)
        item["_signal"] = final_signal
        item["_score"] = agg_score
        item["_window"] = canonical["_window"] if source_posts else representative["_window"]
        item["_group_size"] = len(members)
        item["_source_proxy"] = representative["id"] != key
        item["_aggregate_likes"] = agg_likes
        item["_aggregate_views"] = agg_views
        item["_aggregate_bookmarks"] = agg_bookmarks
        item["_aggregate_quotes"] = agg_quotes
        item["_aggregate_score"] = agg_score
        item["_aggregate_interaction_rate"] = round(
            agg_likes / agg_views if agg_views > 0 else 0.0, 4
        )
        item["_canonical_id"] = key
        item["_canonical_url"] = canonical_url(canonical)
        item["_canonical_author"] = canonical_author(canonical)
        item["_canonical_text"] = canonical_text(canonical)
        item["_anchor_time"] = anchor_time.isoformat()
        item["_external_links"], item["_strong_links"] = collect_group_links(members)
        related_urls: list[str] = []
        seen_related_urls: set[str] = set()
        ranked_members = sorted(members, key=lambda post: -post["_base_score"])

        for post in ranked_members:
            append_unique(related_urls, seen_related_urls, author_thread_urls(post))

        for post in ranked_members:
            candidate_url = normalize_x_url(post["url"])
            if candidate_url and candidate_url != normalize_x_url(representative["url"]):
                append_unique(related_urls, seen_related_urls, [candidate_url])

        item["_related_urls"] = related_urls[:5]
        grouped.append(item)

    return grouped


def backfill_qualifies(item: dict) -> bool:
    if item["_window"] != "backfill":
        return False
    return (
        item["_signal"] == "strong"
        or item["_aggregate_likes"] >= 500
        or item["_aggregate_bookmarks"] >= 200
        or item["_aggregate_score"] >= 1200
    )


def apply_author_cap(
    strong: list[dict], medium: list[dict], backfill: list[dict], cap: int = 2
) -> tuple[list[dict], list[dict], list[dict]]:
    author_counts: Counter[str] = Counter()
    selected = {"strong": [], "medium": [], "backfill": []}

    for bucket_name, items in (("strong", strong), ("backfill", backfill), ("medium", medium)):
        for item in items:
            author = item.get("author", "")
            if author_counts[author] >= cap:
                continue
            author_counts[author] += 1
            selected[bucket_name].append(item)

    return selected["strong"], selected["medium"], selected["backfill"]


def strip_internal_datetime(item: dict) -> dict:
    cleaned = dict(item)
    cleaned.pop("_tweet_time", None)
    cleaned.pop("_canonical_key", None)
    cleaned.pop("_base_signal", None)
    cleaned.pop("_base_score", None)
    return cleaned


def filter_posts(
    raw: list[dict],
    now: datetime,
    fresh_hours: float = 24,
    backfill_hours: float = 48,
    top: int = 0,
    config: dict | None = None,
) -> dict:
    strong_thresholds, medium_thresholds = get_signal_thresholds(config or {})

    seen_ids: set[str] = set()
    posts: list[dict] = []
    skipped = Counter()

    for post in raw:
        if post["id"] in seen_ids:
            skipped["duplicate_id"] += 1
            continue
        seen_ids.add(post["id"])
        posts.append(post)

    candidates: list[dict] = []
    for post in posts:
        if is_noise(post):
            skipped["noise"] += 1
            continue
        if is_self_promo(post):
            skipped["self_promo"] += 1
            continue

        candidate = build_candidate(
            post, now, fresh_hours, backfill_hours, strong_thresholds, medium_thresholds
        )
        if candidate is None:
            skipped["outside_window_or_invalid_time"] += 1
            continue
        candidates.append(candidate)

    grouped = group_candidates(candidates, strong_thresholds, medium_thresholds)
    grouped = [item for item in grouped if item["_signal"] is not None]

    strong = sorted(
        [item for item in grouped if item["_window"] == "fresh" and item["_signal"] == "strong"],
        key=lambda item: (-item["_score"], item["_anchor_time"]),
        reverse=False,
    )
    medium = sorted(
        [item for item in grouped if item["_window"] == "fresh" and item["_signal"] == "medium"],
        key=lambda item: (-item["_score"], item["_anchor_time"]),
        reverse=False,
    )
    backfill = sorted(
        [item for item in grouped if backfill_qualifies(item)],
        key=lambda item: (-item["_score"], item["_anchor_time"]),
        reverse=False,
    )

    strong, medium, backfill = apply_author_cap(strong, medium, backfill)

    if top:
        strong = strong[:top]
        medium = medium[:top]
        backfill = backfill[:top]

    result = {
        "stats": {
            "total_raw": len(raw),
            "unique": len(posts),
            "within_window": len(candidates),
            "grouped_candidates": len(grouped),
            "strong": len(strong),
            "medium": len(medium),
            "backfill": len(backfill),
            "skipped": sum(skipped.values()),
            "skipped_breakdown": dict(skipped),
        },
        "strong": [strip_internal_datetime(item) for item in strong],
        "medium": [strip_internal_datetime(item) for item in medium],
        "backfill": [strip_internal_datetime(item) for item in backfill],
    }
    return result


def parse_args():
    parser = argparse.ArgumentParser(description="Filter X list raw JSON by engagement")
    parser.add_argument("input", help="Raw JSON file from x_list_fetch.py")
    parser.add_argument("--config", help="Path to SOURCE_CONFIG with signal_thresholds")
    parser.add_argument(
        "--top", type=int, default=0, help="Only show top N items per bucket (0 = all)"
    )
    parser.add_argument("--fresh-hours", type=float, default=24, help="Fresh window size in hours")
    parser.add_argument(
        "--backfill-hours", type=float, default=48, help="Backfill window size in hours"
    )
    parser.add_argument("--now", default=None, help="Reference time for fresh/backfill splits")
    parser.add_argument(
        "--output", type=Path, default=None, help="Path to write filtered JSON output (recommended)"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    input_path = Path(args.input).expanduser()
    daily_dir = input_path.parent
    append_run_log(
        skill="x-news-data-pipeline",
        script="filter.py",
        event="step_start",
        message="starting filter",
        meta={
            "input": input_path,
            "config": args.config,
            "fresh_hours": args.fresh_hours,
            "backfill_hours": args.backfill_hours,
            "now": args.now,
        },
        daily_dir=daily_dir,
    )
    if not input_path.exists():
        append_run_log(
            skill="x-news-data-pipeline",
            script="filter.py",
            event="step_failed",
            status="error",
            message="raw.json not found",
            meta={"input": input_path},
            daily_dir=daily_dir,
        )
        print(f"Error: raw.json not found: {input_path}", file=sys.stderr)
        sys.exit(1)
    if args.backfill_hours <= args.fresh_hours:
        append_run_log(
            skill="x-news-data-pipeline",
            script="filter.py",
            event="step_failed",
            status="error",
            message="invalid time windows",
            meta={
                "fresh_hours": args.fresh_hours,
                "backfill_hours": args.backfill_hours,
            },
            daily_dir=daily_dir,
        )
        print("Error: --backfill-hours must be larger than --fresh-hours", file=sys.stderr)
        sys.exit(1)

    config = load_source_config(args.config)
    try:
        raw = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        append_run_log(
            skill="x-news-data-pipeline",
            script="filter.py",
            event="step_failed",
            status="error",
            message="raw.json is not valid JSON",
            meta={"input": input_path, "error": str(exc)},
            daily_dir=daily_dir,
        )
        print(f"Error: raw.json is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(1)
    now = parse_cli_time(args.now) or datetime.now(timezone.utc)
    result = filter_posts(
        raw,
        now=now,
        fresh_hours=args.fresh_hours,
        backfill_hours=args.backfill_hours,
        top=args.top,
        config=config,
    )

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write("\n")
    else:
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        print()

    stats = result["stats"]
    print(
        f"[filter] {stats['total_raw']} raw → {stats['unique']} unique → "
        f"strong={stats['strong']} medium={stats['medium']} backfill={stats['backfill']} "
        f"skipped={stats['skipped']}",
        file=sys.stderr,
    )
    append_run_log(
        skill="x-news-data-pipeline",
        script="filter.py",
        event="step_complete",
        message="filtered raw tweets",
        meta={
            "input": input_path,
            "output_path": os.environ.get("FILTERED_PATH", ""),
            "total_raw": stats["total_raw"],
            "unique": stats["unique"],
            "strong": stats["strong"],
            "medium": stats["medium"],
            "backfill": stats["backfill"],
            "skipped": stats["skipped"],
        },
        daily_dir=daily_dir,
    )


if __name__ == "__main__":
    main()
