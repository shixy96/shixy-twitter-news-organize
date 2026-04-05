#!/usr/bin/env python3
"""
Stage 3: Editorial Review for x-news-quality-audit.

Editorial review dimensions:
- Readability: title format, first paragraph length (>=45 chars), no long paragraphs
- Fact robustness: assertion vs uncertainty word consistency
- Completeness: no placeholders, no missing images, links complete
- Daily post feel: balanced categories, no theme clustering

Usage:
    python3 editorial_review.py --post <path>

Exit codes:
    0 - All checks passed
    1 - One or more checks failed
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[3]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from x_news_shared import append_run_log

# Title should follow: {核心要点}【AI 资讯日报 {DATE}】
TITLE_PATTERN = re.compile(r".+【AI 资讯日报 \d{4}-\d{2}-\d{2}】")

# Assertion words that indicate confidence
ASSERTION_WORDS = {"是", "确定", "肯定", "绝对", "明确", "已经", "完成", "实现"}

# Uncertainty words that indicate doubt
UNCERTAINTY_WORDS = {"可能", "似乎", "大概", "也许", "或许", "不确定", "疑似", "据说"}

# Placeholder patterns
PLACEHOLDER_PATTERNS = [
    r"\[TODO\]",
    r"\[待填充\]",
    r"\[placeholder\]",
    r"TBD",
    r"待定",
    r"xxx",
]


def check_title_format(post: dict) -> list[str]:
    """Check title format."""
    errors = []
    title = post.get("title", "")

    if not title:
        errors.append("title: missing")
        return errors

    if not TITLE_PATTERN.match(title):
        errors.append(
            f"title: format should be '{{核心要点}}【AI 资讯日报 {{DATE}}】', got: {title!r}"
        )

    return errors


def check_paragraph_length(text: str | None, min_length: int = 45) -> bool:
    """Check if first paragraph meets minimum length."""
    if not text:
        return False
    first_para = text.split("\n")[0].strip()
    return len(first_para) >= min_length


def check_no_long_paragraphs(text: str | None, max_length: int = 220) -> bool:
    """Check that no paragraph exceeds max length."""
    if not text:
        return True
    for para in text.split("\n"):
        if len(para.strip()) > max_length:
            return False
    return True


def check_readability(post: dict) -> list[str]:
    """Check readability metrics."""
    errors = []

    categories = post.get("categories", [])
    for cat_idx, cat in enumerate(categories, start=1):
        items = cat.get("items", [])
        for item_idx, item in enumerate(items, start=1):
            body = item.get("body", "")
            ref_index = item.get("index", "?")

            # First paragraph length
            first_para = body.split("\n")[0].strip() if body else ""
            if len(first_para) < 45:
                errors.append(
                    f"items[{ref_index}].body: first paragraph too short "
                    f"({len(first_para)} chars, need >=45)"
                )

            # No very long paragraphs
            for para_idx, para in enumerate(body.split("\n")):
                if len(para.strip()) > 220:
                    errors.append(
                        f"items[{ref_index}].body: paragraph {para_idx + 1} too long "
                        f"({len(para)} chars, need <=220)"
                    )

    return errors


def check_fact_robustness(post: dict) -> list[str]:
    """Check assertion vs uncertainty word consistency."""
    errors = []

    categories = post.get("categories", [])
    for cat in categories:
        items = cat.get("items", [])
        for item in items:
            body = item.get("body", "")
            ref_index = item.get("index", "?")

            if not body:
                continue

            # Count assertion and uncertainty words
            assertion_count = sum(1 for w in ASSERTION_WORDS if w in body)
            uncertainty_count = sum(1 for w in UNCERTAINTY_WORDS if w in body)

            # If both are high, flag as inconsistency
            if assertion_count > 0 and uncertainty_count > 0:
                errors.append(
                    f"items[{ref_index}].body: mixes assertion words ({assertion_count}) "
                    f"with uncertainty words ({uncertainty_count})"
                )

    return errors


def check_completeness(post: dict, base_dir: Path) -> list[str]:
    """Check for placeholders and missing content."""
    errors = []

    body_text = ""
    categories = post.get("categories", [])
    for cat in categories:
        items = cat.get("items", [])
        for item in items:
            body_text += " " + item.get("body", "")

    # Check for placeholders
    for pattern in PLACEHOLDER_PATTERNS:
        if re.search(pattern, body_text, re.IGNORECASE):
            errors.append(f"completeness: found placeholder pattern '{pattern}'")

    for cat in categories:
        items = cat.get("items", [])
        for item in items:
            ref_index = item.get("index", "?")
            if not (item.get("body") or "").strip():
                errors.append(f"items[{ref_index}].body: empty")
            if not (item.get("link") or "").strip():
                errors.append(f"items[{ref_index}].link: empty")

            for rel_idx, rel_link in enumerate(item.get("related_links", []), start=1):
                if not isinstance(rel_link, dict) or not (rel_link.get("url") or "").strip():
                    errors.append(
                        f"items[{ref_index}].related_links[{rel_idx}]: missing url"
                    )

            for media_idx, media_path in enumerate(item.get("media", []), start=1):
                resolved_path = base_dir / media_path
                if not resolved_path.exists():
                    errors.append(
                        f"items[{ref_index}].media[{media_idx}]: missing file '{media_path}'"
                    )

    return errors


def check_daily_post_feel(post: dict) -> list[str]:
    """Check for balanced categories and theme clustering."""
    errors = []

    categories = post.get("categories", [])
    if not categories:
        errors.append("categories: empty")
        return errors

    # Check category balance
    cat_counts = {}
    for cat in categories:
        cat_name = cat.get("name", "unknown")
        cat_counts[cat_name] = len(cat.get("items", []))

    # Warn if one category dominates (>60% of items)
    total_items = sum(cat_counts.values())
    if total_items > 0:
        for cat_name, count in cat_counts.items():
            ratio = count / total_items
            if ratio > 0.6:
                errors.append(
                    f"daily_post_feel: category '{cat_name}' has {ratio:.0%} of items "
                    f"(>60%), may indicate theme clustering"
                )

    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage 3: Editorial Review")
    parser.add_argument("--post", type=Path, required=True, help="Path to post.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    daily_dir = args.post.expanduser().parent
    append_run_log(
        skill="x-news-quality-audit",
        script="editorial_review.py",
        event="step_start",
        message="starting editorial review",
        meta={"post": args.post},
        daily_dir=daily_dir,
    )

    # Load post.json
    try:
        with open(args.post, encoding="utf-8") as f:
            post = json.load(f)
    except FileNotFoundError:
        append_run_log(
            skill="x-news-quality-audit",
            script="editorial_review.py",
            event="step_failed",
            status="error",
            message="post.json not found",
            meta={"post": args.post},
            daily_dir=daily_dir,
        )
        print(f"FAIL: post.json not found: {args.post}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        append_run_log(
            skill="x-news-quality-audit",
            script="editorial_review.py",
            event="step_failed",
            status="error",
            message="post.json is not valid JSON",
            meta={"post": args.post, "error": str(e)},
            daily_dir=daily_dir,
        )
        print(f"FAIL: post.json is not valid JSON: {e}", file=sys.stderr)
        return 1

    all_errors: list[str] = []

    # Run all checks
    all_errors.extend(check_title_format(post))
    all_errors.extend(check_readability(post))
    all_errors.extend(check_fact_robustness(post))
    all_errors.extend(check_completeness(post, args.post.parent))
    all_errors.extend(check_daily_post_feel(post))

    if all_errors:
        append_run_log(
            skill="x-news-quality-audit",
            script="editorial_review.py",
            event="step_warning",
            status="warn",
            message="editorial review produced warnings",
            meta={"warning_count": len(all_errors)},
            daily_dir=daily_dir,
        )
        for error in all_errors:
            print(f"WARN: {error}", file=sys.stderr)
        print(f"\nEDITORIAL_REVIEW: {len(all_errors)} warnings", file=sys.stderr)
        # Editorial review warnings don't fail the pipeline
        # They're suggestions for human review
        append_run_log(
            skill="x-news-quality-audit",
            script="editorial_review.py",
            event="step_complete",
            message="finished editorial review with warnings",
            meta={"warning_count": len(all_errors)},
            daily_dir=daily_dir,
        )
        return 0

    append_run_log(
        skill="x-news-quality-audit",
        script="editorial_review.py",
        event="validate_pass",
        message="editorial review passed",
        meta={},
        daily_dir=daily_dir,
    )
    append_run_log(
        skill="x-news-quality-audit",
        script="editorial_review.py",
        event="step_complete",
        message="finished editorial review",
        meta={},
        daily_dir=daily_dir,
    )
    print("EDITORIAL_REVIEW: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
