#!/usr/bin/env python3
"""
Stage 2: Contract Validation for x-news-quality-audit.

Validates cross-reference integrity:
- companion.json items ↔ filtered.json candidates
- post.json items ↔ companion.json items

Usage:
    python3 stage_contract.py \
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

from x_news_shared import append_run_log, normalize_x_url


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


def build_filtered_index(filtered: dict) -> dict[str, dict]:
    """Build index of filtered candidates by canonical_id and URLs."""
    index: dict[str, dict] = {}
    candidates = (
        filtered.get("strong", []) + filtered.get("medium", []) + filtered.get("backfill", [])
    )
    for c in candidates:
        cid = c.get("_canonical_id")
        if cid:
            index[cid] = c
        url = c.get("url")
        if url:
            norm = normalize_x_url(url)
            if norm:
                index[norm] = c
    return index


def validate_companion_to_filtered(companion: dict, filtered_index: dict) -> list[str]:
    """Validate companion items trace back to filtered candidates."""
    errors = []

    items = companion.get("items", [])
    for item in items:
        idx = item.get("index", "?")
        cid = item.get("canonical_id", "")
        primary = item.get("primary_url", "")

        found = cid in filtered_index
        if not found and primary:
            norm = normalize_x_url(primary)
            if norm:
                found = norm in filtered_index

        if not found:
            errors.append(
                f"companion.items[{idx}]: cannot trace to filtered candidate "
                f"(canonical_id={cid!r}, primary_url={primary!r})"
            )

    return errors


def build_companion_index(companion: dict) -> dict[int, dict]:
    """Build index of companion items by index."""
    return {item.get("index"): item for item in companion.get("items", [])}


def validate_post_to_companion(post: dict, companion_index: dict) -> list[str]:
    """Validate post items trace back to companion items."""
    errors = []

    categories = post.get("categories", [])
    seen_indices: set[int] = set()

    for cat_idx, cat in enumerate(categories, start=1):
        items = cat.get("items", [])
        for item_idx, item in enumerate(items, start=1):
            ref_index = item.get("index")

            if ref_index is None:
                errors.append(f"post.categories[{cat_idx}].items[{item_idx}]: missing 'index'")
                continue

            if ref_index in seen_indices:
                errors.append(
                    f"post.categories[{cat_idx}].items[{item_idx}]: duplicate index {ref_index}"
                )

            if ref_index not in companion_index:
                errors.append(
                    f"post.categories[{cat_idx}].items[{item_idx}]: "
                    f"index {ref_index} not in companion"
                )
            else:
                seen_indices.add(ref_index)
                # Check category consistency
                orig = companion_index[ref_index]
                if item.get("category") != orig.get("category"):
                    # This is a warning, not error - categories can be reorganized
                    pass

    # Check all companion items are in post
    companion_indices = set(companion_index.keys())
    missing = companion_indices - seen_indices
    if missing:
        errors.append(f"post: missing items with indices: {sorted(missing)}")

    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage 2: Contract Validation")
    parser.add_argument("--filtered", type=Path, required=True, help="Path to filtered.json")
    parser.add_argument("--companion", type=Path, required=True, help="Path to companion.json")
    parser.add_argument("--post", type=Path, required=True, help="Path to post.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    daily_dir = args.post.expanduser().parent
    append_run_log(
        skill="x-news-quality-audit",
        script="stage_contract.py",
        event="step_start",
        message="starting contract validation",
        meta={
            "filtered": args.filtered,
            "companion": args.companion,
            "post": args.post,
        },
        daily_dir=daily_dir,
    )

    all_errors: list[str] = []

    # Load filtered
    filtered, err = load_json(args.filtered)
    if err:
        append_run_log(
            skill="x-news-quality-audit",
            script="stage_contract.py",
            event="step_failed",
            status="error",
            message="failed to load filtered.json",
            meta={"filtered": args.filtered, "error": err},
            daily_dir=daily_dir,
        )
        print(f"FAIL: {err}", file=sys.stderr)
        return 1

    # Load companion
    companion, err = load_json(args.companion)
    if err:
        append_run_log(
            skill="x-news-quality-audit",
            script="stage_contract.py",
            event="step_failed",
            status="error",
            message="failed to load companion.json",
            meta={"companion": args.companion, "error": err},
            daily_dir=daily_dir,
        )
        print(f"FAIL: {err}", file=sys.stderr)
        return 1

    # Load post
    post, err = load_json(args.post)
    if err:
        append_run_log(
            skill="x-news-quality-audit",
            script="stage_contract.py",
            event="step_failed",
            status="error",
            message="failed to load post.json",
            meta={"post": args.post, "error": err},
            daily_dir=daily_dir,
        )
        print(f"FAIL: {err}", file=sys.stderr)
        return 1

    # Validate companion -> filtered
    filtered_index = build_filtered_index(filtered)
    errors = validate_companion_to_filtered(companion, filtered_index)
    all_errors.extend([f"companion->filtered: {e}" for e in errors])

    # Validate post -> companion
    companion_index = build_companion_index(companion)
    errors = validate_post_to_companion(post, companion_index)
    all_errors.extend([f"post->companion: {e}" for e in errors])

    if all_errors:
        append_run_log(
            skill="x-news-quality-audit",
            script="stage_contract.py",
            event="step_failed",
            status="error",
            message="contract validation failed",
            meta={"error_count": len(all_errors)},
            daily_dir=daily_dir,
        )
        for error in all_errors:
            print(f"FAIL: {error}", file=sys.stderr)
        print(f"\nCONTRACT_VALIDATION: {len(all_errors)} errors found", file=sys.stderr)
        return 1

    append_run_log(
        skill="x-news-quality-audit",
        script="stage_contract.py",
        event="validate_pass",
        message="contract validation passed",
        meta={},
        daily_dir=daily_dir,
    )
    append_run_log(
        skill="x-news-quality-audit",
        script="stage_contract.py",
        event="step_complete",
        message="finished contract validation",
        meta={},
        daily_dir=daily_dir,
    )
    print("CONTRACT_VALIDATION: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
