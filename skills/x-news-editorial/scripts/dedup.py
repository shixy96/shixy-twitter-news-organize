#!/usr/bin/env python3
"""
Deduplication script for x-news-editorial.

Reads filtered.json and historical companion.json files to produce dedup_result.json
categorizing each candidate as auto_resolved, history_prior_match, or require_decision.

Usage:
    python3 dedup.py --filtered <path> [--prior-companions <path1> [<path2> ...]]

Output:
    dedup_result.json to stdout

Exit codes:
    0 - Success
    1 - Invalid arguments or processing error
"""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from x_news_shared import append_run_log, normalize_x_url


def load_companion_items(companion_path: Path) -> list[dict]:
    """Load items from a companion.json file."""
    try:
        with open(companion_path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("items", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def get_canonical_id(item: dict) -> str:
    """Get canonical ID from an item."""
    return item.get("canonical_id", item.get("id", ""))


def get_x_urls(item: dict) -> set[str]:
    """Get all X URLs from an item."""
    urls = set()

    primary_url = item.get("primary_url")
    if primary_url:
        normalized = normalize_x_url(primary_url)
        if normalized:
            urls.add(normalized)

    related_urls = item.get("related_urls", [])
    for url in related_urls:
        normalized = normalize_x_url(url)
        if normalized:
            urls.add(normalized)

    return urls


def get_reference_links(item: dict) -> set[str]:
    """Get non-X reference links from an item."""
    links = set()

    strong_links = item.get("strong_links", [])
    for link in strong_links:
        if isinstance(link, dict):
            url = link.get("url")
        else:
            url = link
        if url and not normalize_x_url(url):
            links.add(url)

    external_links = item.get("external_links", [])
    for link in external_links:
        if isinstance(link, dict):
            url = link.get("url")
        else:
            url = link
        if url and not normalize_x_url(url):
            links.add(url)

    return links


def build_history_index(history_items: list[dict]) -> dict[str, dict]:
    """Build an index of history items by their X URLs and reference links.

    Items are processed newest-first (as passed by caller). For duplicate
    canonical_ids, we keep the first (newest) occurrence.
    """
    index = {}
    for item in history_items:
        canonical_id = get_canonical_id(item)
        if canonical_id and canonical_id not in index:
            index[canonical_id] = item

        for url in get_x_urls(item):
            if url not in index:
                index[url] = item

        for link in get_reference_links(item):
            if link not in index:
                index[link] = item

    return index


def check_new_content(item: dict, history_item: dict) -> tuple[bool, str]:
    """Check if item has new content compared to history_item.

    Returns:
        (has_new_content, delta_summary)
    """
    new_links = []
    new_text = False

    item_urls = get_x_urls(item)
    history_urls = get_x_urls(history_item)

    new_x_urls = item_urls - history_urls
    if new_x_urls:
        new_links.append(f"新 X URL: {list(new_x_urls)[0]}")

    item_text = item.get("summary", "") or item.get("text", "")
    history_text = history_item.get("summary", "") or history_item.get("text", "")
    if item_text != history_text and item_text:
        new_text = True
        new_links.append("正文内容有更新")

    item_links = get_reference_links(item)
    history_links = get_reference_links(history_item)
    new_ref_links = item_links - history_links
    if new_ref_links:
        new_links.append(f"新参考链接: {list(new_ref_links)[0]}")

    return bool(new_links), " / ".join(new_links) if new_links else "无明显新增内容"


def group_by_event(candidates: list[dict]) -> dict[str, list[dict]]:
    """Group candidates by canonical_id (same event/story)."""
    groups: dict[str, list[dict]] = {}
    for candidate in candidates:
        canonical_id = get_canonical_id(candidate)
        if canonical_id not in groups:
            groups[canonical_id] = []
        groups[canonical_id].append(candidate)
    return groups


def lookup_history_match(
    candidate: dict, history_index: dict[str, dict]
) -> tuple[dict | None, str | None]:
    """Look up a candidate in the history index using multiple keys.

    Tries canonical_id, normalized X URLs (primary + related), and reference links.
    Returns (matched_history_item, match_signature) or (None, None).

    Args:
        candidate: Filtered candidate item
        history_index: History index built by build_history_index

    Returns:
        (matched_item, match_signature) tuple
    """
    # Try canonical_id first
    canonical_id = get_canonical_id(candidate)
    if canonical_id:
        matched = history_index.get(canonical_id)
        if matched:
            return matched, f"canonical_id:{canonical_id}"

    # Try X URLs
    for url in get_x_urls(candidate):
        matched = history_index.get(url)
        if matched:
            return matched, f"x_url:{url}"

    # Try reference links
    for link in get_reference_links(candidate):
        matched = history_index.get(link)
        if matched:
            return matched, f"ref_link:{link}"

    return None, None


def process_dedup(
    filtered_path: Path,
    prior_companion_paths: list[Path],
) -> dict:
    """Process deduplication against history.

    Args:
        filtered_path: Path to filtered.json
        prior_companion_paths: List of paths to historical companion.json files (newest first)

    Returns:
        dedup_result dict
    """
    # Load filtered candidates
    with open(filtered_path, encoding="utf-8") as f:
        filtered_data = json.load(f)

    candidates = (
        filtered_data.get("strong", [])
        + filtered_data.get("medium", [])
        + filtered_data.get("backfill", [])
    )

    # Build history index from all prior companions
    history_items: list[dict] = []
    for path in prior_companion_paths:
        history_items.extend(load_companion_items(path))

    history_index = build_history_index(history_items)

    # Group candidates by event
    event_groups = group_by_event(candidates)

    auto_resolved = []
    history_prior_match = []
    require_decision = []
    by_author: dict[str, list[dict]] = {}

    for canonical_id, group_candidates in event_groups.items():
        # Check if any candidate matches history using multiple signatures
        matched_history, match_sig = lookup_history_match(group_candidates[0], history_index)

        if matched_history:
            # Check for new content
            has_new_content, delta_summary = check_new_content(group_candidates[0], matched_history)

            history_prior_match.append(
                {
                    "canonical_id": canonical_id,
                    "prior_item": matched_history,
                    "match_signature": match_sig,
                    "has_new_content_delta": has_new_content,
                    "delta_summary": delta_summary,
                    "reason": "历史已有相同事件（通过 {} 匹配），需判断是否为有效跟进".format(
                        match_sig
                    ),
                }
            )
        elif len(group_candidates) > 1:
            # Multiple candidates for same event need decision
            require_decision.append(
                {
                    "canonical_id": canonical_id,
                    "candidates": group_candidates,
                    "reason": "需要判断哪条更相关",
                }
            )
        else:
            # Single candidate, auto-resolve
            auto_resolved.append(
                {
                    "canonical_id": canonical_id,
                    "dedup_type": "new_candidate",
                    "reason": "新事件，无历史重叠",
                }
            )

        # Group by author for tracking
        for candidate in group_candidates:
            author = candidate.get("author", "unknown")
            if author not in by_author:
                by_author[author] = []
            by_author[author].append(candidate)

    result = {
        "auto_resolved": auto_resolved,
        "history_prior_match": history_prior_match,
        "require_decision": require_decision,
        "by_author": {author: len(items) for author, items in by_author.items()},
    }

    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Deduplicate filtered candidates against historical companions"
    )
    parser.add_argument(
        "--filtered",
        type=Path,
        required=True,
        help="Path to filtered.json",
    )
    parser.add_argument(
        "--prior-companions",
        type=Path,
        nargs="*",
        default=[],
        help="Paths to historical companion.json files (newest first)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    daily_dir = args.filtered.expanduser().parent
    append_run_log(
        skill="x-news-editorial",
        script="dedup.py",
        event="step_start",
        message="starting dedup",
        meta={
            "filtered": args.filtered,
            "prior_companions": [str(path) for path in args.prior_companions],
        },
        daily_dir=daily_dir,
    )

    if not args.filtered.exists():
        append_run_log(
            skill="x-news-editorial",
            script="dedup.py",
            event="step_failed",
            status="error",
            message="filtered.json not found",
            meta={"filtered": args.filtered},
            daily_dir=daily_dir,
        )
        print(f"Error: filtered.json not found: {args.filtered}", file=sys.stderr)
        return 1

    for path in args.prior_companions:
        if not path.exists():
            append_run_log(
                skill="x-news-editorial",
                script="dedup.py",
                event="history_missing",
                status="warn",
                message="historical companion missing",
                meta={"path": path},
                daily_dir=daily_dir,
            )
            print(f"Warning: companion.json not found: {path}", file=sys.stderr)

    result = process_dedup(args.filtered, args.prior_companions)

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    print()

    # Print summary to stderr
    print(
        f"[dedup] auto={len(result['auto_resolved'])} "
        f"history_match={len(result['history_prior_match'])} "
        f"require_decision={len(result['require_decision'])}",
        file=sys.stderr,
    )
    append_run_log(
        skill="x-news-editorial",
        script="dedup.py",
        event="step_complete",
        message="dedup result generated",
        meta={
            "output_path": os.environ.get("DEDUP_RESULT_PATH", ""),
            "auto_resolved": len(result["auto_resolved"]),
            "history_prior_match": len(result["history_prior_match"]),
            "require_decision": len(result["require_decision"]),
        },
        daily_dir=daily_dir,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
