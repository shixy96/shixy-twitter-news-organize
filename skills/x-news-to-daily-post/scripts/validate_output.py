#!/usr/bin/env python3
"""
Validate post.json output for x-news-to-daily-post.

Validates frontmatter fields, category grouping, item count consistency,
no markdown residue, and highlight item enrichment coverage.

Usage:
    python3 validate_output.py --post-json <path> --companion <path> [--enrichment <path>]

Exit codes:
    0 - Validation passed
    1 - Validation failed
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from x_news_shared import ALLOWED_CATEGORIES, append_run_log


# Required frontmatter fields
REQUIRED_FRONTMATTER = {"title", "description", "pubDate", "tags", "slug"}

# Markdown patterns that should not be in body
MARKDOWN_RESIDUE_PATTERNS = [
    (r"^\s*>\s*\*\*\[重点关注\]\*\*", "highlight marker in body"),
    (r"^\s*-\s+要点:", "bullet point format"),
]

TITLE_PLACEHOLDER_PATTERNS = [
    r"^\s*$",
    r"^\s*(h[1-6]|标题|title)\s*$",
    r"^\s*(示例|样例|待补充|tbd|todo)\s*$",
]


def validate_frontmatter(post: dict) -> list[str]:
    """Validate frontmatter fields."""
    errors = []

    for field in REQUIRED_FRONTMATTER:
        if field not in post:
            errors.append(f"frontmatter: missing required field '{field}'")

    # Validate tags is array
    tags = post.get("tags")
    if tags is not None and not isinstance(tags, list):
        errors.append(f"frontmatter.tags: must be array, got {type(tags).__name__}")

    # Validate slug format
    slug = post.get("slug")
    if slug and not re.match(r"^[a-z0-9-]+$", slug):
        errors.append(
            f"frontmatter.slug: must be lowercase alphanumeric with hyphens, got: {slug!r}"
        )

    return errors


def validate_categories(categories: list, companion_items: list) -> list[str]:
    """Validate category grouping is correct.

    Args:
        categories: Categories from post.json
        companion_items: Items from companion.json

    Returns:
        List of error messages
    """
    errors = []

    if not isinstance(categories, list):
        errors.append("categories: must be array")
        return errors

    # Build set of all item indices from companion
    companion_indices = {item.get("index") for item in companion_items}
    seen_indices: set[int] = set()

    for cat_idx, cat in enumerate(categories, start=1):
        if not isinstance(cat, dict):
            errors.append(f"categories[{cat_idx}]: must be object")
            continue

        cat_name = cat.get("name", "")
        if cat_name and cat_name not in ALLOWED_CATEGORIES:
            errors.append(f"categories[{cat_idx}].name: invalid category '{cat_name}'")

        cat_items = cat.get("items", [])
        if not isinstance(cat_items, list):
            errors.append(f"categories[{cat_idx}].items: must be array")
            continue

        for item_idx, item in enumerate(cat_items, start=1):
            if not isinstance(item, dict):
                errors.append(f"categories[{cat_idx}].items[{item_idx}]: must be object")
                continue

            ref_index = item.get("index")
            if ref_index is None:
                errors.append(f"categories[{cat_idx}].items[{item_idx}]: missing 'index'")
            elif ref_index in seen_indices:
                errors.append(
                    f"categories[{cat_idx}].items[{item_idx}]: duplicate index {ref_index}"
                )
            elif ref_index not in companion_indices:
                errors.append(
                    f"categories[{cat_idx}].items[{item_idx}]: index {ref_index} not in companion"
                )
            else:
                seen_indices.add(ref_index)

    # Check all companion items are represented
    missing = companion_indices - seen_indices
    if missing:
        errors.append(f"categories: missing items with indices: {sorted(missing)}")

    return errors


def validate_body_content(body: str | None, index: int) -> list[str]:
    """Validate body content has no markdown residue.

    Args:
        body: Body content
        index: Item index for error messages

    Returns:
        List of error messages
    """
    errors = []

    if not isinstance(body, str):
        errors.append(f"items[{index}].body: must be string")
        return errors

    for pattern, description in MARKDOWN_RESIDUE_PATTERNS:
        if re.search(pattern, body, re.MULTILINE):
            errors.append(f"items[{index}].body: contains {description}")

    return errors


def normalize_title_for_comparison(title: str) -> str:
    """Normalize title text for exact-match checks."""
    return " ".join(title.strip().lower().split())


def validate_item_title(item: dict, companion_item: dict | None, index: int) -> list[str]:
    """Validate item title is present and rewritten by the agent."""
    errors = []
    title = item.get("title")

    if not isinstance(title, str):
        return [f"items[{index}].title: must be string"]

    for pattern in TITLE_PLACEHOLDER_PATTERNS:
        if re.match(pattern, title, re.IGNORECASE):
            errors.append(f"items[{index}].title: placeholder or empty title is not allowed")
            return errors

    if companion_item is not None:
        companion_title = companion_item.get("title")
        if isinstance(companion_title, str):
            if normalize_title_for_comparison(title) == normalize_title_for_comparison(companion_title):
                errors.append(
                    f"items[{index}].title: must be rewritten for post.json, "
                    "not copied verbatim from companion.json"
                )

    return errors


def validate_post_json(
    post_json_path: Path, companion_path: Path, enrichment_path: Path | None
) -> list[str]:
    """Main validation function.

    Args:
        post_json_path: Path to post.json
        companion_path: Path to companion.json
        enrichment_path: Optional path to enrichment.json

    Returns:
        List of error messages
    """
    errors = []

    # Load post.json
    try:
        with open(post_json_path, encoding="utf-8") as f:
            post = json.load(f)
    except FileNotFoundError:
        return [f"post.json not found: {post_json_path}"]
    except json.JSONDecodeError as e:
        return [f"post.json is not valid JSON: {e}"]

    # Load companion.json
    try:
        with open(companion_path, encoding="utf-8") as f:
            companion = json.load(f)
    except FileNotFoundError:
        return [f"companion.json not found: {companion_path}"]
    except json.JSONDecodeError as e:
        return [f"companion.json is not valid JSON: {e}"]

    # Validate frontmatter
    errors.extend(validate_frontmatter(post))

    # Load enrichment if provided
    enrichment = None
    if enrichment_path and enrichment_path.exists():
        try:
            with open(enrichment_path, encoding="utf-8") as f:
                enrichment = json.load(f)
        except json.JSONDecodeError:
            pass

    # Validate categories
    companion_items = companion.get("items", [])
    categories = post.get("categories", [])
    errors.extend(validate_categories(categories, companion_items))

    # Validate items in categories
    companion_by_index = {
        item.get("index"): item for item in companion_items if isinstance(item, dict)
    }

    for cat_idx, cat in enumerate(categories):
        cat_items = cat.get("items", [])
        for item_idx, item in enumerate(cat_items):
            ref_index = item.get("index")
            companion_item = companion_by_index.get(ref_index)
            errors.extend(validate_item_title(item, companion_item, ref_index or 0))
            body = item.get("body", "")
            errors.extend(validate_body_content(body, ref_index or 0))

            # Validate highlight item enrichment coverage if enrichment provided
            if enrichment and ref_index:
                companion_item = next(
                    (c for c in companion_items if c.get("index") == ref_index), None
                )
                if companion_item and companion_item.get("is_highlight"):
                    enrichment_item = next(
                        (e for e in enrichment.get("items", []) if e.get("index") == ref_index),
                        None,
                    )
                    if enrichment_item:
                        fetch_status = enrichment_item.get("fetch_status", {})
                        primary_status = fetch_status.get("primary_url", "unknown")
                        if primary_status != "success":
                            errors.append(
                                f"highlight item {ref_index}: primary_url_fetch is "
                                f"{primary_status} - blocking warning "
                                f"(highlight requires enrichment coverage)"
                            )

    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate post.json output")
    parser.add_argument("--post-json", type=Path, required=True, help="Path to post.json")
    parser.add_argument("--companion", type=Path, required=True, help="Path to companion.json")
    parser.add_argument(
        "--enrichment", type=Path, default=None, help="Path to enrichment.json (optional)"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    daily_dir = args.post_json.expanduser().parent
    append_run_log(
        skill="x-news-to-daily-post",
        script="validate_output.py",
        event="step_start",
        message="starting post validation",
        meta={
            "post_json": args.post_json,
            "companion": args.companion,
            "enrichment": args.enrichment,
        },
        daily_dir=daily_dir,
    )

    errors = validate_post_json(args.post_json, args.companion, args.enrichment)

    if errors:
        append_run_log(
            skill="x-news-to-daily-post",
            script="validate_output.py",
            event="step_failed",
            status="error",
            message="post validation failed",
            meta={
                "post_json": args.post_json,
                "companion": args.companion,
                "enrichment": args.enrichment,
                "error_count": len(errors),
            },
            daily_dir=daily_dir,
        )
        for error in errors:
            print(f"Error: {error}", file=sys.stderr)
        return 1

    append_run_log(
        skill="x-news-to-daily-post",
        script="validate_output.py",
        event="validate_pass",
        message="post validation passed",
        meta={"post_json": args.post_json},
        daily_dir=daily_dir,
    )
    append_run_log(
        skill="x-news-to-daily-post",
        script="validate_output.py",
        event="step_complete",
        message="finished post validation",
        meta={"post_json": args.post_json},
        daily_dir=daily_dir,
    )
    print("POST_VALIDATION_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
