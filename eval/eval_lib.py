#!/usr/bin/env python3
"""
Eval library for shixy-twitter-news-organize.

Provides evaluation and benchmark aggregation for x-news-digest.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
EVAL_ROOT = REPO_ROOT / "eval"
EVAL_RUNS_ROOT = EVAL_ROOT / "runs"

ALLOWED_CATEGORIES = {
    "模型发布",
    "开发生态",
    "技术洞察",
    "产品动态",
    "安全事件",
    "行业观点",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_json(p: Path, data: Any) -> None:
    ensure_dir(p.parent)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_json(p: Path) -> Any:
    return json.loads(p.read_text(encoding="utf-8"))


def short_id() -> str:
    return uuid.uuid4().hex[:6]


def timestamp_token() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S")


def contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def pairwise_jaccard(sets: list[set[str]]) -> float | None:
    if len(sets) < 2:
        return None
    scores = []
    for a, b in combinations(sets, 2):
        union = a | b
        if union:
            scores.append(len(a & b) / len(union))
    return sum(scores) / len(scores) if scores else None


# ---------------------------------------------------------------------------
# Evaluate: x-news-digest
# ---------------------------------------------------------------------------


def evaluate_digest(artifacts_dir: Path) -> dict:
    """Validate post.json quality."""
    post_path = artifacts_dir / "post.json"
    errors, warnings = [], []
    status = "PASS"

    if not post_path.exists():
        return {"skill": "x-news-digest", "status": "FAIL", "errors": ["post.json missing"]}

    try:
        post = load_json(post_path)
    except json.JSONDecodeError as e:
        return {"skill": "x-news-digest", "status": "FAIL", "errors": [f"invalid JSON: {e}"]}

    if not isinstance(post, dict):
        return {"skill": "x-news-digest", "status": "FAIL", "errors": ["not an object"]}

    # Check frontmatter
    for field in ("title", "description", "pubDate", "tags", "slug", "categories"):
        if field not in post:
            errors.append(f"missing '{field}'")
            status = "FAIL"

    categories = post.get("categories", [])
    items = []
    selected_ids = []
    for cat in categories:
        if not isinstance(cat, dict):
            errors.append(f"invalid category: not a dict")
            status = "FAIL"
            continue
        cat_name = cat.get("name", "")
        if cat_name not in ALLOWED_CATEGORIES:
            errors.append(f"invalid category: {cat_name}")
            status = "FAIL"
        for item in cat.get("items", []):
            items.append(item)

    item_checks = []
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            issues = ["item_not_dict"]
            cid = f"invalid-{idx}"
            selected_ids.append(cid)
            item_checks.append({"canonical_id": cid, "title": "", "issues": issues})
            if status != "FAIL":
                status = "FAIL"
            continue
        cid = item.get("canonical_id")
        issues = []
        if not cid:
            cid = f"missing-{idx}"
            issues.append("missing_canonical_id")
        else:
            cid = str(cid)
        selected_ids.append(cid)

        # Title checks
        title = item.get("title", "")
        body = item.get("body", "")
        if not contains_cjk(title):
            issues.append("title_not_chinese")
        if len(title) > 50:
            issues.append("title_too_long")

        # Body checks
        if not contains_cjk(body):
            issues.append("body_not_chinese")
        body_len = len(body)
        if body_len < 80:
            issues.append("body_too_short")

        # Placeholder checks
        if re.search(r"(TODO|TBD|xxx|待补充|placeholder)", body, re.IGNORECASE):
            issues.append("has_placeholder")

        if issues:
            if status != "FAIL":
                status = (
                    "FAIL"
                    if any(
                        i
                        in (
                            "title_not_chinese",
                            "body_not_chinese",
                            "has_placeholder",
                            "item_not_dict",
                            "missing_canonical_id",
                        )
                        for i in issues
                    )
                    else "WARN"
                )

        item_checks.append({"canonical_id": cid, "title": title, "issues": issues})

    # Item count check
    item_count = len(items)
    if item_count < 8:
        warnings.append(f"only {item_count} items (target: 8-12)")
    elif item_count > 12:
        warnings.append(f"{item_count} items exceeds target max 12")

    return {
        "skill": "x-news-digest",
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "item_count": item_count,
        "selected_ids": selected_ids,
        "item_checks": item_checks,
    }


# ---------------------------------------------------------------------------
# Benchmark
# ---------------------------------------------------------------------------


def build_benchmark(skill: str, case: dict, metrics_list: list[dict]) -> dict:
    statuses = [m.get("status", "UNKNOWN") for m in metrics_list]
    bench = {
        "skill": skill,
        "case_id": case.get("id", ""),
        "report_date": case.get("report_date", ""),
        "runs": len(metrics_list),
        "statuses": statuses,
        "pass_count": statuses.count("PASS"),
        "warn_count": statuses.count("WARN"),
        "fail_count": statuses.count("FAIL"),
    }

    if skill == "x-news-digest":
        selected_sets = [set(m.get("selected_ids", [])) for m in metrics_list]
        bench["avg_pairwise_jaccard"] = pairwise_jaccard(selected_sets)

        # Digest-specific metrics
        from collections import Counter

        item_counts = [m.get("item_count", 0) for m in metrics_list]
        bench["item_count_mean"] = _mean(item_counts)
        bench["item_count_std"] = _std(item_counts)

        all_ids = []
        for m in metrics_list:
            all_ids.extend(m.get("selected_ids", []))
        bench["selection_frequency"] = dict(Counter(all_ids))

    return bench


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    variance = sum((x - m) ** 2 for x in values) / (len(values) - 1)
    return variance**0.5
