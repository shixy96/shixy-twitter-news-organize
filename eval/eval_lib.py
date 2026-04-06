#!/usr/bin/env python3
"""
Eval library for x-news-skills.

Provides fixture-based evaluation and benchmark aggregation for:
- x-news-fetch: validates filtered.json structure
- x-news-digest: validates post.json quality (Chinese titles, body length, categories)
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
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


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


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
# Invocation management
# ---------------------------------------------------------------------------


def create_invocation_dir(report_date: str, mode: str) -> Path:
    run_root = ensure_dir(EVAL_RUNS_ROOT / report_date)
    while True:
        name = f"{timestamp_token()}-{mode}-{short_id()}"
        d = run_root / name
        if not d.exists():
            ensure_dir(d / "results")
            return d


def resolve_fixture_path(value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else (REPO_ROOT / value).resolve()


def stage_fixtures(case: dict, artifacts_dir: Path) -> None:
    for target, source in (case.get("artifacts") or {}).items():
        src = resolve_fixture_path(source)
        if not src.exists():
            raise FileNotFoundError(f"fixture missing: {source}")
        ensure_dir(artifacts_dir.parent)
        if src.is_dir():
            if (artifacts_dir / target).exists():
                shutil.rmtree(artifacts_dir / target)
            shutil.copytree(src, artifacts_dir / target)
        else:
            ensure_dir((artifacts_dir / target).parent)
            shutil.copy2(src, artifacts_dir / target)


# ---------------------------------------------------------------------------
# Case loading
# ---------------------------------------------------------------------------


def load_case(skill: str, case_id: str) -> dict:
    return load_json(EVAL_ROOT / "cases" / skill / f"{case_id}.json")


def load_suite(suite_id: str) -> dict:
    return load_json(EVAL_ROOT / "cases" / "suites" / f"{suite_id}.json")


def list_skill_cases(skill: str) -> list[dict]:
    d = EVAL_ROOT / "cases" / skill
    if not d.exists():
        return []
    cases = []
    for p in d.glob("*.json"):
        try:
            cases.append(load_json(p))
        except (json.JSONDecodeError, FileNotFoundError):
            pass
    return sorted(cases, key=lambda c: c.get("report_date", ""))


def list_suites() -> list[dict]:
    d = EVAL_ROOT / "cases" / "suites"
    if not d.exists():
        return []
    suites = []
    for p in d.glob("*.json"):
        try:
            suites.append(load_json(p))
        except (json.JSONDecodeError, FileNotFoundError):
            pass
    return sorted(suites, key=lambda s: s.get("report_date", ""))


# ---------------------------------------------------------------------------
# Evaluate: x-news-fetch
# ---------------------------------------------------------------------------


def evaluate_fetch(artifacts_dir: Path) -> dict:
    """Validate filtered.json structure."""
    filtered_path = artifacts_dir / "filtered.json"
    errors, status = [], "PASS"

    if not filtered_path.exists():
        return {"skill": "x-news-fetch", "status": "FAIL", "errors": ["filtered.json missing"]}

    try:
        data = load_json(filtered_path)
    except json.JSONDecodeError as e:
        return {"skill": "x-news-fetch", "status": "FAIL", "errors": [f"invalid JSON: {e}"]}

    if not isinstance(data, dict):
        return {"skill": "x-news-fetch", "status": "FAIL", "errors": ["not an object"]}

    for key in ("stats", "strong", "medium", "backfill"):
        if key not in data:
            errors.append(f"missing '{key}'")
            status = "FAIL"

    candidate_ids = []
    for bucket in ("strong", "medium", "backfill"):
        for item in data.get(bucket, []):
            cid = item.get("_canonical_id") or item.get("id")
            if cid:
                candidate_ids.append(str(cid))

    return {
        "skill": "x-news-fetch",
        "status": status,
        "errors": errors,
        "stats": data.get("stats", {}),
        "candidate_ids": candidate_ids,
        "candidate_count": len(candidate_ids),
        "sha256": sha256_file(filtered_path),
    }


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
        cat_name = cat.get("name", "")
        if cat_name not in ALLOWED_CATEGORIES:
            errors.append(f"invalid category: {cat_name}")
            status = "FAIL"
        for item in cat.get("items", []):
            items.append(item)

    item_checks = []
    for item in items:
        cid = str(item.get("canonical_id") or item.get("index", "?"))
        selected_ids.append(cid)
        title = item.get("title", "")
        body = item.get("body", "")
        issues = []

        # Title checks
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
            status = (
                "FAIL"
                if any(
                    i in ("title_not_chinese", "body_not_chinese", "has_placeholder")
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

    if skill == "x-news-fetch":
        candidate_sets = [set(m.get("candidate_ids", [])) for m in metrics_list]
        bench["avg_pairwise_jaccard"] = pairwise_jaccard(candidate_sets)
    elif skill == "x-news-digest":
        selected_sets = [set(m.get("selected_ids", [])) for m in metrics_list]
        bench["avg_pairwise_jaccard"] = pairwise_jaccard(selected_sets)

    return bench


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_suite_report_markdown(report: dict) -> str:
    lines = [
        "# X News Eval Suite Report",
        "",
        f"- Overall: `{report['overall_status']}`",
        "",
        "## Skills",
    ]
    for row in report.get("skills", []):
        lines.append(f"- `{row['skill']}`: `{row['status']}`")
    return "\n".join(lines) + "\n"
