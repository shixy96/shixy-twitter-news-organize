#!/usr/bin/env python3
"""
Stage 1: JSON Schema Validation for x-news-quality-audit.

Validates schema for raw.json, filtered.json, companion.json, post.json.

Usage:
    python3 stage_json_validate.py \
      --raw <path> \
      --filtered <path> \
      --companion <path> \
      --post <path>

Exit codes:
    0 - All validations passed
    1 - One or more validations failed
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[3]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from x_news_shared import (
    COMPANION_SCHEMA,
    FILTERED_SCHEMA,
    POST_SCHEMA,
    append_run_log,
    validate_json_schema,
)


def load_json(path: Path) -> tuple[Any | None, str | None]:
    """Load JSON file.

    Returns:
        (data, error_message)
    """
    if not path.exists():
        return None, f"File not found: {path}"
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f), None
    except json.JSONDecodeError as e:
        return None, f"Invalid JSON: {e}"


def validate_raw(raw_path: Path) -> list[str]:
    """Validate raw.json."""
    errors = []
    data, err = load_json(raw_path)
    if err:
        return [f"raw.json: {err}"]

    if not isinstance(data, list):
        errors.append("raw.json: must be array")
        return errors

    # Basic structure check
    required = {"id", "url", "author", "text", "time"}
    for i, item in enumerate(data[:10]):  # Check first 10
        if not isinstance(item, dict):
            errors.append(f"raw.json[{i}]: must be object")
            continue
        missing = required - set(item.keys())
        if missing:
            errors.append(f"raw.json[{i}]: missing fields: {', '.join(missing)}")

    return errors


def validate_filtered(filtered_path: Path) -> list[str]:
    """Validate filtered.json against schema."""
    errors = []
    data, err = load_json(filtered_path)
    if err:
        return [f"filtered.json: {err}"]

    schema_errors = validate_json_schema(data, FILTERED_SCHEMA)
    errors.extend([f"filtered.json: {e}" for e in schema_errors])

    # Stats consistency checks (filtered.json has no stats.total, so we only check bucket counts)
    if isinstance(data, dict):
        stats = data.get("stats", {})
        buckets = ["strong", "medium", "backfill"]
        # Verify stats counts match actual bucket lengths
        for bucket in buckets:
            stat_count = stats.get(bucket, 0)
            bucket_count = len(data.get(bucket, []))
            if stat_count != bucket_count:
                errors.append(
                    f"filtered.json: stats.{bucket} ({stat_count}) != "
                    f"len({bucket}) ({bucket_count})"
                )

    return errors


def validate_companion(companion_path: Path) -> list[str]:
    """Validate companion.json against schema."""
    errors = []
    data, err = load_json(companion_path)
    if err:
        return [f"companion.json: {err}"]

    schema_errors = validate_json_schema(data, COMPANION_SCHEMA)
    errors.extend([f"companion.json: {e}" for e in schema_errors])

    # Stats consistency checks
    if isinstance(data, dict):
        stats = data.get("stats", {})
        items = data.get("items", [])

        # Check stats.total == strong + medium + backfill
        strong = stats.get("strong", 0)
        medium = stats.get("medium", 0)
        backfill = stats.get("backfill", 0)
        total = stats.get("total", 0)
        expected_total = strong + medium + backfill
        if total != expected_total:
            errors.append(
                f"companion.json: stats.total ({total}) != "
                f"strong+medium+backfill ({expected_total})"
            )

        # Check stats.selected == len(items)
        selected = stats.get("selected")
        if isinstance(selected, int) and selected != len(items):
            errors.append(
                f"companion.json: stats.selected ({selected}) != len(items) ({len(items)})"
            )

    return errors


def validate_post(post_path: Path) -> list[str]:
    """Validate post.json against schema."""
    errors = []
    data, err = load_json(post_path)
    if err:
        return [f"post.json: {err}"]

    schema_errors = validate_json_schema(data, POST_SCHEMA)
    errors.extend([f"post.json: {e}" for e in schema_errors])

    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage 1: JSON Schema Validation")
    parser.add_argument("--raw", type=Path, default=None, help="Path to raw.json")
    parser.add_argument("--filtered", type=Path, default=None, help="Path to filtered.json")
    parser.add_argument("--companion", type=Path, default=None, help="Path to companion.json")
    parser.add_argument("--post", type=Path, default=None, help="Path to post.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    daily_dir = None
    for candidate in (args.raw, args.filtered, args.companion, args.post):
        if candidate is not None:
            daily_dir = candidate.expanduser().parent
            break
    append_run_log(
        skill="x-news-quality-audit",
        script="stage_json_validate.py",
        event="step_start",
        message="starting json schema validation",
        meta={
            "raw": args.raw,
            "filtered": args.filtered,
            "companion": args.companion,
            "post": args.post,
        },
        daily_dir=daily_dir,
    )

    all_errors: list[str] = []

    if args.raw:
        errors = validate_raw(args.raw)
        all_errors.extend(errors)

    if args.filtered:
        errors = validate_filtered(args.filtered)
        all_errors.extend(errors)

    if args.companion:
        errors = validate_companion(args.companion)
        all_errors.extend(errors)

    if args.post:
        errors = validate_post(args.post)
        all_errors.extend(errors)

    if all_errors:
        append_run_log(
            skill="x-news-quality-audit",
            script="stage_json_validate.py",
            event="step_failed",
            status="error",
            message="json schema validation failed",
            meta={"error_count": len(all_errors)},
            daily_dir=daily_dir,
        )
        for error in all_errors:
            print(f"FAIL: {error}", file=sys.stderr)
        print(f"\nJSON_VALIDATION: {len(all_errors)} errors found", file=sys.stderr)
        return 1

    append_run_log(
        skill="x-news-quality-audit",
        script="stage_json_validate.py",
        event="validate_pass",
        message="json schema validation passed",
        meta={},
        daily_dir=daily_dir,
    )
    append_run_log(
        skill="x-news-quality-audit",
        script="stage_json_validate.py",
        event="step_complete",
        message="finished json schema validation",
        meta={},
        daily_dir=daily_dir,
    )
    print("JSON_VALIDATION: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
