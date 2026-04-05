#!/usr/bin/env python3
"""
Validate raw.json is a valid JSON array of tweet objects.

Usage:
    python3 raw_validate.py --input <path>

Exit codes:
    0 - Valid JSON, valid schema
    1 - Invalid JSON or schema validation failed
    2 - Missing required argument
"""

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from x_news_shared import RAW_SCHEMA, append_run_log, validate_json_schema


def validate_raw_json(data: list) -> list[str]:
    """Validate raw.json array contents.

    Args:
        data: Parsed JSON data (should be list)

    Returns:
        List of validation errors
    """
    errors = []

    if not isinstance(data, list):
        return [f"root: expected array, got {type(data).__name__}"]

    required_fields = {"id", "url", "author", "text", "time"}

    for i, item in enumerate(data):
        if not isinstance(item, dict):
            errors.append(f"[{i}]: expected object, got {type(item).__name__}")
            continue

        # Check required fields
        for field in required_fields:
            if field not in item:
                errors.append(f"[{i}]: missing required field '{field}'")

        # Validate types of known fields
        if "id" in item and not isinstance(item["id"], str):
            errors.append(f"[{i}].id: expected string, got {type(item['id']).__name__}")
        if "url" in item and not isinstance(item["url"], str):
            errors.append(f"[{i}].url: expected string, got {type(item['url']).__name__}")
        if "author" in item and not isinstance(item["author"], str):
            errors.append(f"[{i}].author: expected string, got {type(item['author']).__name__}")
        if "text" in item and not isinstance(item["text"], str):
            errors.append(f"[{i}].text: expected string, got {type(item['text']).__name__}")
        if "time" in item and not isinstance(item["time"], str):
            errors.append(f"[{i}].time: expected string, got {type(item['time']).__name__}")

        # Validate optional numeric fields
        for field in ["likes", "views", "bookmarks", "quotes", "replies", "retweets"]:
            if field in item and not isinstance(item[field], int):
                errors.append(f"[{i}].{field}: expected integer, got {type(item[field]).__name__}")

        # Validate arrays
        for field in ["links", "media", "thread_reply_ids"]:
            if field in item and not isinstance(item[field], list):
                errors.append(f"[{i}].{field}: expected array, got {type(item[field]).__name__}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate raw.json format")
    parser.add_argument("--input", required=True, help="Path to raw.json file")
    args = parser.parse_args()

    input_path = Path(args.input)
    daily_dir = input_path.expanduser().parent
    append_run_log(
        skill="x-news-data-pipeline",
        script="raw_validate.py",
        event="step_start",
        message="starting raw validation",
        meta={"input": input_path},
        daily_dir=daily_dir,
    )

    # Check file exists
    if not input_path.exists():
        append_run_log(
            skill="x-news-data-pipeline",
            script="raw_validate.py",
            event="step_failed",
            status="error",
            message="raw.json not found",
            meta={"input": input_path},
            daily_dir=daily_dir,
        )
        print(f"Error: File not found: {input_path}", file=sys.stderr)
        return 1

    # Load and parse JSON
    try:
        with open(input_path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        append_run_log(
            skill="x-news-data-pipeline",
            script="raw_validate.py",
            event="step_failed",
            status="error",
            message="raw.json is not valid JSON",
            meta={"input": input_path, "error": str(e)},
            daily_dir=daily_dir,
        )
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        return 1

    # Validate structure
    errors = validate_raw_json(data)
    if errors:
        append_run_log(
            skill="x-news-data-pipeline",
            script="raw_validate.py",
            event="step_failed",
            status="error",
            message="raw validation failed",
            meta={"input": input_path, "error_count": len(errors)},
            daily_dir=daily_dir,
        )
        for error in errors:
            print(f"Error: {error}", file=sys.stderr)
        return 1

    # Validate against schema
    schema_errors = validate_json_schema(data, {"type": "array", "items": RAW_SCHEMA})
    if schema_errors:
        append_run_log(
            skill="x-news-data-pipeline",
            script="raw_validate.py",
            event="step_failed",
            status="error",
            message="raw schema validation failed",
            meta={"input": input_path, "error_count": len(schema_errors)},
            daily_dir=daily_dir,
        )
        for error in schema_errors:
            print(f"Error: {error}", file=sys.stderr)
        return 1

    append_run_log(
        skill="x-news-data-pipeline",
        script="raw_validate.py",
        event="validate_pass",
        message="raw validation passed",
        meta={"input": input_path, "item_count": len(data)},
        daily_dir=daily_dir,
    )
    append_run_log(
        skill="x-news-data-pipeline",
        script="raw_validate.py",
        event="step_complete",
        message="finished raw validation",
        meta={"input": input_path, "item_count": len(data)},
        daily_dir=daily_dir,
    )
    print(f"RAW_JSON_OK ({len(data)} items)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
