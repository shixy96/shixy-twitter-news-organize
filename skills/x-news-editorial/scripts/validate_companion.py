#!/usr/bin/env python3
"""
Validate companion.json for x-news-editorial.

Validates schema, stats consistency, items traceability, and title format.

Usage:
    python3 validate_companion.py --companion <path> --filtered <path>

Exit codes:
    0 - Validation passed
    1 - Validation failed
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from x_news_shared import ALLOWED_CATEGORIES, append_run_log, normalize_x_url


# Title format: {核心要点}【AI 资讯日报 {DATE}】
TITLE_PATTERN = re.compile(r".+【AI 资讯日报 \d{4}-\d{2}-\d{2}】")


def validate_generated_at(value: str | None) -> list[str]:
    """Validate generated_at field."""
    errors = []
    if not isinstance(value, str):
        errors.append("companion.json: 'generated_at' must be a string")
        return errors
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"companion.json: 'generated_at' is not valid ISO 8601: {value!r}")
    return errors


def validate_stats(companion: dict, filtered: dict) -> list[str]:
    """Validate stats consistency between companion and filtered."""
    errors = []

    stats = companion.get("stats", {})
    filtered_strong = len(filtered.get("strong", []))
    filtered_medium = len(filtered.get("medium", []))
    filtered_backfill = len(filtered.get("backfill", []))

    expected_total = filtered_strong + filtered_medium + filtered_backfill

    checks = [
        ("strong", stats.get("strong"), filtered_strong),
        ("medium", stats.get("medium"), filtered_medium),
        ("backfill", stats.get("backfill"), filtered_backfill),
        ("total", stats.get("total"), expected_total),
    ]

    for key, actual, expected in checks:
        if not isinstance(actual, int):
            errors.append(f"companion.stats.{key}: must be integer, got {type(actual).__name__}")
        elif actual != expected:
            errors.append(f"companion.stats.{key}: expected {expected}, got {actual}")

    return errors


def validate_selection_window(companion: dict, filtered: dict) -> list[str]:
    """Validate selected item count stays within the editorial target window."""
    errors = []
    items = companion.get("items", [])
    total_candidates = (
        len(filtered.get("strong", []))
        + len(filtered.get("medium", []))
        + len(filtered.get("backfill", []))
    )
    selected_count = len(items)

    if total_candidates >= 8 and selected_count < 8:
        errors.append(
            f"companion.items: selected {selected_count} items, expected at least 8 "
            f"when {total_candidates} candidates are available"
        )

    max_allowed = min(total_candidates, 12)
    if selected_count > max_allowed:
        errors.append(
            f"companion.items: selected {selected_count} items, expected at most "
            f"{max_allowed} from {total_candidates} candidates"
        )

    return errors


def validate_items_schema(items: list) -> list[str]:
    """Validate items array schema."""
    errors = []

    required_fields = {
        "index",
        "canonical_id",
        "title",
        "author",
        "author_screen_name",
        "category",
        "is_highlight",
        "summary",
        "metrics",
        "primary_url",
        "strong_links",
        "external_links",
        "related_urls",
        "is_backfill",
        "is_followup",
    }

    for i, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            errors.append(f"companion.items[{i}]: must be object, got {type(item).__name__}")
            continue

        missing = sorted(required_fields - set(item.keys()))
        if missing:
            errors.append(f"companion.items[{i}]: missing fields: {', '.join(missing)}")

        if item.get("index") != i:
            errors.append(f"companion.items[{i}].index: expected {i}, got {item.get('index')}")

        category = item.get("category")
        if category and category not in ALLOWED_CATEGORIES:
            errors.append(f"companion.items[{i}].category: invalid category '{category}'")

        metrics = item.get("metrics", {})
        if isinstance(metrics, dict):
            for key in ("likes", "views", "bookmarks"):
                if key in metrics and not isinstance(metrics[key], int):
                    errors.append(f"companion.items[{i}].metrics.{key}: must be integer")

    return errors


def validate_title(title: str | None, report_date: str | None) -> list[str]:
    """Validate dynamic title format."""
    errors = []

    if not isinstance(title, str):
        errors.append("companion.title: must be string")
        return errors

    if not TITLE_PATTERN.match(title):
        errors.append(
            f"companion.title: format must be '{{核心要点}}【AI 资讯日报 {{DATE}}】', got: {title!r}"
        )

    if report_date:
        expected_suffix = f"【AI 资讯日报 {report_date}】"
        if not title.endswith(expected_suffix):
            errors.append(f"companion.title: must end with '{expected_suffix}', got: {title!r}")

    return errors


def build_candidate_index(filtered: dict) -> dict[str, dict]:
    """Build an index of filtered candidates by various IDs."""
    index: dict[str, dict] = {}
    candidates = (
        filtered.get("strong", []) + filtered.get("medium", []) + filtered.get("backfill", [])
    )

    for candidate in candidates:
        canonical_id = candidate.get("_canonical_id")
        if canonical_id:
            index[canonical_id] = candidate

        url = candidate.get("url")
        if url:
            normalized = normalize_x_url(url)
            if normalized:
                index[normalized] = candidate

        canonical_url = candidate.get("_canonical_url")
        if canonical_url:
            normalized = normalize_x_url(canonical_url)
            if normalized:
                index[normalized] = candidate

    return index


def validate_items_traceability(items: list, candidate_index: dict) -> list[str]:
    """Validate that items can be traced back to filtered candidates."""
    errors = []

    for i, item in enumerate(items, start=1):
        canonical_id = item.get("canonical_id", "")
        primary_url = item.get("primary_url", "")

        found = False
        if canonical_id in candidate_index:
            found = True
        elif primary_url:
            normalized = normalize_x_url(primary_url)
            if normalized and normalized in candidate_index:
                found = True

        if not found:
            errors.append(
                f"companion.items[{i}]: cannot trace to any filtered candidate "
                f"(canonical_id={canonical_id!r}, primary_url={primary_url!r})"
            )

    return errors


def validate_categories(categories: list | None, items: list) -> list[str]:
    """Validate categories are derived correctly from items."""
    errors = []

    if not isinstance(categories, list):
        errors.append("companion.categories: must be array")
        return errors

    # Build items index by index number
    items_by_index = {item["index"]: item for item in items if isinstance(item, dict)}
    seen_indices: set[int] = set()

    for cat_idx, cat in enumerate(categories, start=1):
        if not isinstance(cat, dict):
            errors.append(f"companion.categories[{cat_idx}]: must be object")
            continue

        cat_name = cat.get("name")
        if cat_name and cat_name not in ALLOWED_CATEGORIES:
            errors.append(f"companion.categories[{cat_idx}].name: invalid category '{cat_name}'")

        cat_items = cat.get("items", [])
        if not isinstance(cat_items, list):
            errors.append(f"companion.categories[{cat_idx}].items: must be array")
            continue

        for item_idx, cat_item in enumerate(cat_items, start=1):
            if not isinstance(cat_item, dict):
                errors.append(f"companion.categories[{cat_idx}].items[{item_idx}]: must be object")
                continue

            ref_index = cat_item.get("index")
            if ref_index is None:
                errors.append(
                    f"companion.categories[{cat_idx}].items[{item_idx}]: missing 'index' field"
                )
            elif ref_index in seen_indices:
                errors.append(
                    f"companion.categories[{cat_idx}].items[{item_idx}]: duplicate index {ref_index}"
                )
            elif ref_index not in items_by_index:
                errors.append(
                    f"companion.categories[{cat_idx}].items[{item_idx}]: "
                    f"index {ref_index} not found in items"
                )
            else:
                seen_indices.add(ref_index)
                expected_category = items_by_index[ref_index].get("category")
                if cat_name != expected_category:
                    errors.append(
                        f"companion.categories[{cat_idx}].items[{item_idx}]: "
                        f"category section '{cat_name}' does not match items[{ref_index}] "
                        f"category '{expected_category}'"
                    )
                item_category = cat_item.get("category")
                if item_category is not None and item_category != expected_category:
                    errors.append(
                        f"companion.categories[{cat_idx}].items[{item_idx}]: "
                        f"category mismatch with items[{ref_index}]"
                    )

    missing_indices = sorted(set(items_by_index) - seen_indices)
    if missing_indices:
        errors.append(
            f"companion.categories: missing items with indices: {missing_indices}"
        )

    return errors


def validate_companion(companion_path: Path, filtered_path: Path) -> list[str]:
    """Main validation function."""
    errors = []

    # Load companion
    try:
        with open(companion_path, encoding="utf-8") as f:
            companion = json.load(f)
    except FileNotFoundError:
        return [f"companion.json not found: {companion_path}"]
    except json.JSONDecodeError as e:
        return [f"companion.json is not valid JSON: {e}"]

    # Load filtered
    try:
        with open(filtered_path, encoding="utf-8") as f:
            filtered = json.load(f)
    except FileNotFoundError:
        return [f"filtered.json not found: {filtered_path}"]
    except json.JSONDecodeError as e:
        return [f"filtered.json is not valid JSON: {e}"]

    # Validate generated_at
    errors.extend(validate_generated_at(companion.get("generated_at")))

    # Validate report_date
    report_date = companion.get("report_date")
    if not isinstance(report_date, str):
        errors.append("companion.report_date: must be string")

    # Validate title
    errors.extend(validate_title(companion.get("title"), report_date))

    # Validate stats
    errors.extend(validate_stats(companion, filtered))

    # Validate items schema
    items = companion.get("items", [])
    if not isinstance(items, list):
        errors.append("companion.items: must be array")
        return errors

    errors.extend(validate_items_schema(items))

    # Validate selected count matches items length
    stats = companion.get("stats", {})
    if isinstance(stats.get("selected"), int) and stats["selected"] != len(items):
        errors.append(f"companion.stats.selected: {stats['selected']} != len(items): {len(items)}")

    # Validate editorial selection window
    errors.extend(validate_selection_window(companion, filtered))

    # Validate items traceability
    if errors:
        return errors

    candidate_index = build_candidate_index(filtered)
    errors.extend(validate_items_traceability(items, candidate_index))

    # Validate categories
    errors.extend(validate_categories(companion.get("categories"), items))

    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate companion.json format")
    parser.add_argument("--companion", type=Path, required=True, help="Path to companion.json")
    parser.add_argument("--filtered", type=Path, required=True, help="Path to filtered.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    daily_dir = args.companion.expanduser().parent
    append_run_log(
        skill="x-news-editorial",
        script="validate_companion.py",
        event="step_start",
        message="starting companion validation",
        meta={"companion": args.companion, "filtered": args.filtered},
        daily_dir=daily_dir,
    )

    errors = validate_companion(args.companion, args.filtered)

    if errors:
        append_run_log(
            skill="x-news-editorial",
            script="validate_companion.py",
            event="step_failed",
            status="error",
            message="companion validation failed",
            meta={
                "companion": args.companion,
                "filtered": args.filtered,
                "error_count": len(errors),
            },
            daily_dir=daily_dir,
        )
        for error in errors:
            print(f"Error: {error}", file=sys.stderr)
        return 1

    append_run_log(
        skill="x-news-editorial",
        script="validate_companion.py",
        event="validate_pass",
        message="companion validation passed",
        meta={"companion": args.companion, "filtered": args.filtered},
        daily_dir=daily_dir,
    )
    append_run_log(
        skill="x-news-editorial",
        script="validate_companion.py",
        event="step_complete",
        message="finished companion validation",
        meta={"companion": args.companion},
        daily_dir=daily_dir,
    )
    print("REPORT_VALIDATION_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
