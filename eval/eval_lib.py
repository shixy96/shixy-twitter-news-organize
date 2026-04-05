#!/usr/bin/env python3
"""
Eval library for x-news-skills.

Provides reusable helpers for running skill evaluations with fixture-based
regression testing and benchmark aggregation.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import math
import re
import shutil
import sys
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any

# x-news-skills repo root
REPO_ROOT = Path(__file__).resolve().parent.parent
EVAL_ROOT = REPO_ROOT / "eval"
EVAL_RUNS_ROOT = EVAL_ROOT / "runs"

from x_news_shared import ALLOWED_CATEGORIES

# AI relevance hint terms
AI_HINT_TERMS = {
    "ai",
    "agent",
    "llm",
    "模型",
    "推理",
    "开源",
    "论文",
    "github",
    "arxiv",
    "claude",
    "openai",
    "codex",
    "huggingface",
    "trl",
    "benchmark",
    "安全",
    "机器人",
}


@dataclass
class InvocationPaths:
    """Directory structure for an eval invocation."""

    root: Path
    request_dir: Path
    results_dir: Path
    logs_dir: Path
    summary_dir: Path


# ---------------------------------------------------------------------------
# Path & directory helpers
# ---------------------------------------------------------------------------


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def short_id() -> str:
    return uuid.uuid4().hex[:6]


def timestamp_token(now: datetime | None = None) -> str:
    return (now or datetime.now()).strftime("%Y%m%dT%H%M%S")


def safe_rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


# ---------------------------------------------------------------------------
# Invocation path management
# ---------------------------------------------------------------------------


def create_invocation_paths(report_date: str, mode: str) -> InvocationPaths:
    """Create unique invocation directories for an eval run."""
    run_root = ensure_dir(EVAL_RUNS_ROOT / report_date)
    while True:
        name = f"{timestamp_token()}-{mode}-{short_id()}"
        invocation_root = run_root / name
        if not invocation_root.exists():
            break
    request_dir = ensure_dir(invocation_root / "request")
    results_dir = ensure_dir(invocation_root / "results")
    logs_dir = ensure_dir(invocation_root / "logs")
    summary_dir = ensure_dir(invocation_root / "summary")
    return InvocationPaths(
        root=invocation_root,
        request_dir=request_dir,
        results_dir=results_dir,
        logs_dir=logs_dir,
        summary_dir=summary_dir,
    )


# ---------------------------------------------------------------------------
# Case loading
# ---------------------------------------------------------------------------


def case_path(skill: str, case_id: str) -> Path:
    """Path to a skill-specific case definition."""
    return EVAL_ROOT / "cases" / skill / f"{case_id}.json"


def suite_path(suite_id: str) -> Path:
    """Path to a suite definition."""
    return EVAL_ROOT / "cases" / "suites" / f"{suite_id}.json"


def load_case(skill: str, case_id: str) -> tuple[dict[str, Any], Path]:
    """Load a case definition by skill and case_id."""
    path = case_path(skill, case_id)
    return load_json(path), path


def load_suite(suite_id: str) -> tuple[dict[str, Any], Path]:
    """Load a suite definition by suite_id."""
    path = suite_path(suite_id)
    return load_json(path), path


# ---------------------------------------------------------------------------
# Fixture management
# ---------------------------------------------------------------------------


def resolve_fixture_path(value: str) -> Path:
    """Resolve a fixture path, treating relative paths as relative to REPO_ROOT."""
    path = Path(value)
    if path.is_absolute():
        return path
    return (REPO_ROOT / value).resolve()


def copy_path(source: Path, target: Path) -> None:
    """Copy a file or directory to target."""
    ensure_dir(target.parent)
    if source.is_dir():
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
        return
    shutil.copy2(source, target)


def stage_fixtures(case: dict[str, Any], artifacts_dir: Path) -> None:
    """Copy fixture artifacts to the artifacts directory.

    Args:
        case: Case definition with optional 'artifacts' mapping
        artifacts_dir: Target directory for artifacts
    """
    for relative_target, source_value in (case.get("artifacts") or {}).items():
        source_path = resolve_fixture_path(source_value)
        if not source_path.exists():
            raise FileNotFoundError(f"fixture source missing for {relative_target}: {source_value}")
        copy_path(source_path, artifacts_dir / relative_target)


# ---------------------------------------------------------------------------
# Text analysis helpers
# ---------------------------------------------------------------------------


def normalize_text(value: str) -> str:
    return re.sub(r"[\W_]+", "", value or "").lower()


def text_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return difflib.SequenceMatcher(None, normalize_text(left), normalize_text(right)).ratio()


def contains_cjk(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text or ""))


def looks_ai_relevant(text: str) -> bool:
    haystack = (text or "").lower()
    return any(term in haystack for term in AI_HINT_TERMS)


def sentence_count(text: str) -> int:
    matches = re.findall(r"[。！？!?]+", text or "")
    return len(matches) if matches else (1 if (text or "").strip() else 0)


# ---------------------------------------------------------------------------
# Jaccard similarity
# ---------------------------------------------------------------------------


def pairwise_jaccard(values: list[set[str]]) -> float | None:
    """Compute average pairwise Jaccard similarity across runs."""
    if len(values) < 2:
        return None
    scores: list[float] = []
    for left, right in combinations(values, 2):
        union = left | right
        if not union:
            continue
        scores.append(len(left & right) / len(union))
    if not scores:
        return None
    return sum(scores) / len(scores)


# ---------------------------------------------------------------------------
# Candidate lookups
# ---------------------------------------------------------------------------


def filtered_candidate_ids(filtered_payload: dict[str, Any]) -> list[str]:
    """Extract all candidate IDs from a filtered payload."""
    ids: list[str] = []
    for bucket in ("strong", "medium", "backfill"):
        for item in filtered_payload.get(bucket, []) or []:
            candidate_id = (
                item.get("_canonical_id")
                or item.get("id")
                or item.get("_canonical_url")
                or item.get("url")
            )
            if candidate_id:
                ids.append(str(candidate_id))
    return ids


def editorial_candidate_lookup(filtered_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build a lookup table for filtered candidates."""
    lookup: dict[str, dict[str, Any]] = {}
    for bucket in ("strong", "medium", "backfill"):
        for item in filtered_payload.get(bucket, []) or []:
            identifiers = [
                item.get("_canonical_id"),
                item.get("id"),
                item.get("_canonical_url"),
                item.get("url"),
            ]
            for identifier in identifiers:
                if identifier:
                    lookup[str(identifier)] = item
    return lookup


# ---------------------------------------------------------------------------
# Evaluation: data-pipeline
# ---------------------------------------------------------------------------


def evaluate_data_pipeline_run(run_dir: Path) -> dict[str, Any]:
    """Evaluate a data-pipeline run from artifacts.

    Validates that raw.json and filtered.json exist and have correct structure.
    """
    artifacts_dir = run_dir / "artifacts"
    raw_path = artifacts_dir / "raw.json"
    filtered_path = artifacts_dir / "filtered.json"

    errors: list[str] = []
    warnings: list[str] = []
    failure_codes: list[str] = []
    status = "PASS"

    # Check raw.json
    if not raw_path.exists():
        status = "FAIL"
        failure_codes.append("raw_missing")
        errors.append("raw.json 不存在")
        raw_payload = None
    else:
        try:
            raw_payload = load_json(raw_path)
            if not isinstance(raw_payload, list):
                status = "FAIL"
                failure_codes.append("raw_not_array")
                errors.append("raw.json 顶层必须是数组")
        except json.JSONDecodeError as exc:
            status = "FAIL"
            failure_codes.append("raw_invalid_json")
            errors.append(f"raw.json 不是合法 JSON: {exc}")

    # Check filtered.json
    if not filtered_path.exists():
        status = "FAIL"
        failure_codes.append("filtered_missing")
        errors.append("filtered.json 不存在")
        filtered_payload = None
    else:
        try:
            filtered_payload = load_json(filtered_path)
            if not isinstance(filtered_payload, dict):
                status = "FAIL"
                failure_codes.append("filtered_not_object")
                errors.append("filtered.json 顶层必须是 object")
            else:
                missing_keys = [
                    k
                    for k in ("strong", "medium", "backfill", "stats")
                    if k not in filtered_payload
                ]
                if missing_keys:
                    status = "FAIL"
                    failure_codes.append("filtered_schema_incomplete")
                    errors.append(f"filtered.json 缺少字段: {', '.join(missing_keys)}")
        except json.JSONDecodeError as exc:
            status = "FAIL"
            failure_codes.append("filtered_invalid_json")
            errors.append(f"filtered.json 不是合法 JSON: {exc}")
            filtered_payload = None

    # Extract candidate IDs
    candidate_ids: list[str] = []
    if isinstance(filtered_payload, dict):
        candidate_ids = filtered_candidate_ids(filtered_payload)

    metrics = {
        "skill": "x-news-data-pipeline",
        "status": status,
        "failure_codes": sorted(set(failure_codes)),
        "errors": errors,
        "warnings": warnings,
        "raw": {
            "exists": raw_path.exists(),
            "item_count": len(raw_payload) if isinstance(raw_payload, list) else None,
            "sha256": sha256_file(raw_path) if raw_path.exists() else None,
        },
        "filtered": {
            "exists": filtered_path.exists(),
            "stats": (filtered_payload or {}).get("stats", {}) if filtered_payload else {},
            "candidate_count": len(candidate_ids),
            "sha256": sha256_file(filtered_path) if filtered_path.exists() else None,
        },
        "candidate_ids": candidate_ids,
    }
    write_json(run_dir / "metrics.json", metrics)

    judge = {
        "backend": "rule-based-v1",
        "summary": "数据管道产物的结构检查。",
        "dimensions": [
            {
                "name": "capture_integrity",
                "score": 5 if status == "PASS" else 1,
                "notes": errors[:3] or ["raw/filtered JSON 结构正常。"],
            }
        ],
    }
    write_json(run_dir / "judge.json", judge)
    return metrics


# ---------------------------------------------------------------------------
# Evaluation: editorial
# ---------------------------------------------------------------------------


def detail_issues_in_summary(summary: str, title: str, source_text: str) -> list[str]:
    """Check editorial quality issues in a summary."""
    issues: list[str] = []
    if not contains_cjk(summary):
        issues.append("summary_not_chinese")
    if text_similarity(summary, title) >= 0.82:
        issues.append("summary_title_redundant")
    if source_text and text_similarity(summary, source_text[: len(summary) + 40]) >= 0.82:
        issues.append("summary_near_source_copy")
    if not contains_cjk(summary) or len(summary.strip()) < 15:
        issues.append("summary_too_short")
    return sorted(set(issues))


def evaluate_editorial_run(run_dir: Path) -> dict[str, Any]:
    """Evaluate an editorial run from artifacts.

    Validates companion.json structure and editorial quality.
    """
    artifacts_dir = run_dir / "artifacts"
    filtered_path = artifacts_dir / "filtered.json"
    companion_path = artifacts_dir / "companion.json"

    errors: list[str] = []
    warnings: list[str] = []
    failure_codes: list[str] = []
    status = "PASS"

    # Load filtered
    filtered_payload: dict[str, Any] = {}
    if filtered_path.exists():
        try:
            filtered_payload = load_json(filtered_path)
        except json.JSONDecodeError:
            status = "FAIL"
            failure_codes.append("filtered_invalid_json")
            errors.append("filtered.json 不是合法 JSON")

    # Load companion
    companion_payload: dict[str, Any] = {}
    if not companion_path.exists():
        status = "FAIL"
        failure_codes.append("companion_missing")
        errors.append("companion.json 不存在")
    else:
        try:
            companion_payload = load_json(companion_path)
        except json.JSONDecodeError as exc:
            status = "FAIL"
            failure_codes.append("companion_invalid_json")
            errors.append(f"companion.json 不是合法 JSON: {exc}")

    # Validate companion structure
    if isinstance(companion_payload, dict):
        stats = companion_payload.get("stats", {})
        items = companion_payload.get("items", [])

        # Check required fields
        for field in ("generated_at", "report_date", "title", "stats", "items"):
            if field not in companion_payload:
                status = "FAIL"
                failure_codes.append(f"companion_missing_{field}")
                errors.append(f"companion.json 缺少字段: {field}")

        # Check stats consistency
        if isinstance(stats, dict):
            expected_total = (
                stats.get("strong", 0) + stats.get("medium", 0) + stats.get("backfill", 0)
            )
            if stats.get("total", 0) != expected_total:
                status = "FAIL"
                failure_codes.append("stats_total_mismatch")
                errors.append(
                    f"stats.total ({stats.get('total')}) != strong+medium+backfill ({expected_total})"
                )

            if stats.get("selected", 0) != len(items):
                status = "FAIL"
                failure_codes.append("stats_selected_mismatch")
                errors.append(
                    f"stats.selected ({stats.get('selected')}) != len(items) ({len(items)})"
                )

        # Check items
        candidate_lookup = editorial_candidate_lookup(
            filtered_payload if isinstance(filtered_payload, dict) else {}
        )
        item_checks: list[dict[str, Any]] = []
        selected_ids: list[str] = []
        category_by_id: dict[str, str] = {}
        highlight_by_id: dict[str, bool] = {}

        for item in items:
            if not isinstance(item, dict):
                continue
            canonical_id = str(item.get("canonical_id") or item.get("index", "?"))
            selected_ids.append(canonical_id)
            category_by_id[canonical_id] = item.get("category", "")
            highlight_by_id[canonical_id] = bool(item.get("is_highlight"))

            title = item.get("title", "")
            summary = item.get("summary", "")

            # Get source text from candidate
            source_text = ""
            if canonical_id in candidate_lookup:
                cand = candidate_lookup[canonical_id]
                source_text = cand.get("_canonical_text") or cand.get("text") or ""

            issues = detail_issues_in_summary(summary, title, source_text)
            if issues:
                status = "FAIL"
                failure_codes.extend(issues)

            ai_relevant = looks_ai_relevant(f"{title} {summary}")
            if not ai_relevant:
                warnings.append(f"条目 '{title}' 可能离题")

            item_checks.append(
                {
                    "index": item.get("index"),
                    "canonical_id": canonical_id,
                    "title": title,
                    "summary": summary,
                    "issues": issues,
                    "ai_relevant": ai_relevant,
                }
            )

        thin_items = [c for c in item_checks if c["issues"]]
        off_topic_items = [c for c in item_checks if not c["ai_relevant"]]
        thin_rate = len(thin_items) / len(item_checks) if item_checks else 0.0

        if off_topic_items and status == "PASS":
            status = "WARN"

        metrics = {
            "skill": "x-news-editorial",
            "status": status,
            "failure_codes": sorted(set(failure_codes)),
            "errors": errors,
            "warnings": warnings,
            "selected_ids": selected_ids,
            "category_by_id": category_by_id,
            "highlight_by_id": highlight_by_id,
            "thin_summary_rate": thin_rate,
            "off_topic_rate": len(off_topic_items) / len(item_checks) if item_checks else 0.0,
            "item_checks": item_checks,
        }
    else:
        metrics = {
            "skill": "x-news-editorial",
            "status": "FAIL",
            "failure_codes": sorted(set(failure_codes)),
            "errors": errors,
            "warnings": warnings,
        }

    write_json(run_dir / "metrics.json", metrics)
    thin_items = metrics.get("item_checks", [])
    thin_rate = metrics.get("thin_summary_rate", 0.0)
    judge = {
        "backend": "rule-based-v1",
        "summary": "基于摘要质量和中文化程度的编辑检查。",
        "dimensions": [
            {
                "name": "summary_quality",
                "score": max(1, 5 - math.ceil(thin_rate * 4)),
                "notes": [f"{c['title']}: {', '.join(c['issues'])}" for c in thin_items[:5]]
                or ["摘要基本满足中文化要求。"],
            },
        ],
    }
    write_json(run_dir / "judge.json", judge)
    return metrics


# ---------------------------------------------------------------------------
# Evaluation: daily-post
# ---------------------------------------------------------------------------


def has_overview_section(markdown_text: str) -> bool:
    """Check if markdown has an overview section."""
    return bool(re.search(r"^##\s+(今日要点|概览)\s*$", markdown_text, re.MULTILINE))


def evaluate_daily_post_run(run_dir: Path) -> dict[str, Any]:
    """Evaluate a daily-post run from artifacts.

    Validates post.md structure and coverage.
    """
    artifacts_dir = run_dir / "artifacts"
    companion_path = artifacts_dir / "companion.json"
    post_md_path = artifacts_dir / "post.md"

    errors: list[str] = []
    warnings: list[str] = []
    failure_codes: list[str] = []
    status = "PASS"

    # Load companion
    companion_payload: dict[str, Any] = {}
    if companion_path.exists():
        try:
            companion_payload = load_json(companion_path)
        except json.JSONDecodeError:
            status = "FAIL"
            failure_codes.append("companion_invalid_json")
            errors.append("companion.json 不是合法 JSON")
    else:
        status = "FAIL"
        failure_codes.append("companion_missing")
        errors.append("companion.json 不存在")

    # Load post.md
    post_text = ""
    if post_md_path.exists():
        post_text = post_md_path.read_text(encoding="utf-8")
        overview_present = has_overview_section(post_text)
        if not overview_present:
            warnings.append("缺少概览区")
    else:
        status = "FAIL"
        failure_codes.append("post_missing")
        errors.append("post.md 不存在")

    # Check coverage
    companion_items = (
        companion_payload.get("items", []) if isinstance(companion_payload, dict) else []
    )
    expected_count = len(companion_items)
    actual_count = 0

    # Try to extract item count from post.md
    if post_text:
        # Simple heuristic: count h2/h3 headers after overview
        section_headers = re.findall(r"^##\s+", post_text, re.MULTILINE)
        actual_count = len(section_headers)

    coverage_match = actual_count == expected_count
    if not coverage_match:
        warnings.append(f"post.md 条目数({actual_count})与 companion({expected_count})可能不一致")

    metrics = {
        "skill": "x-news-to-daily-post",
        "status": status,
        "failure_codes": sorted(set(failure_codes)),
        "errors": errors,
        "warnings": warnings,
        "overview_present": has_overview_section(post_text) if post_text else False,
        "expected_item_count": expected_count,
        "actual_item_count": actual_count,
        "coverage_match": coverage_match,
    }
    write_json(run_dir / "metrics.json", metrics)

    judge = {
        "backend": "rule-based-v1",
        "summary": "日报结构和覆盖检查。",
        "dimensions": [
            {
                "name": "structure",
                "score": 5 if status == "PASS" and coverage_match else 3 if status == "PASS" else 1,
                "notes": errors[:3]
                or (
                    ["条目覆盖一致"]
                    if coverage_match
                    else [f"条目覆盖不一致: expected={expected_count}, actual={actual_count}"]
                ),
            }
        ],
    }
    write_json(run_dir / "judge.json", judge)
    return metrics


# ---------------------------------------------------------------------------
# Benchmark aggregation
# ---------------------------------------------------------------------------


def build_benchmark(
    skill: str, case: dict[str, Any], metrics_by_run: list[dict[str, Any]]
) -> dict[str, Any]:
    """Aggregate metrics across multiple runs into a benchmark."""
    statuses = [metrics.get("status", "UNKNOWN") for metrics in metrics_by_run]
    benchmark: dict[str, Any] = {
        "skill": skill,
        "case_id": case["id"],
        "report_date": case["report_date"],
        "runs": len(metrics_by_run),
        "statuses": statuses,
        "pass_count": sum(1 for s in statuses if s == "PASS"),
        "warn_count": sum(1 for s in statuses if s == "WARN"),
        "fail_count": sum(1 for s in statuses if s == "FAIL"),
    }

    if skill == "x-news-data-pipeline":
        candidate_sets = [set(metrics.get("candidate_ids", [])) for metrics in metrics_by_run]
        benchmark["avg_pairwise_jaccard"] = pairwise_jaccard(candidate_sets)
        benchmark["filtered_hashes"] = [
            metrics.get("filtered", {}).get("sha256") for metrics in metrics_by_run
        ]

    elif skill == "x-news-editorial":
        selected_sets = [set(metrics.get("selected_ids", [])) for metrics in metrics_by_run]
        benchmark["avg_pairwise_jaccard"] = pairwise_jaccard(selected_sets)
        benchmark["thin_summary_rates"] = [
            metrics.get("thin_summary_rate", 0.0) for metrics in metrics_by_run
        ]
        benchmark["off_topic_rates"] = [
            metrics.get("off_topic_rate", 0.0) for metrics in metrics_by_run
        ]

    elif skill == "x-news-to-daily-post":
        benchmark["overview_present"] = [
            metrics.get("overview_present", False) for metrics in metrics_by_run
        ]
        benchmark["coverage_matches"] = [
            metrics.get("coverage_match", False) for metrics in metrics_by_run
        ]

    return benchmark


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def render_markdown_list(values: list[str]) -> str:
    if not values:
        return "- 无\n"
    return "".join(f"- {value}\n" for value in values)


def render_skill_analysis(
    skill: str,
    case: dict[str, Any],
    benchmark: dict[str, Any],
    metrics_by_run: list[dict[str, Any]],
) -> str:
    """Render human-readable analysis for a skill."""
    lines = [
        f"# {skill} Analysis",
        "",
        f"- Case: `{case['id']}`",
        f"- Report date: `{case['report_date']}`",
        f"- Runs: `{benchmark['runs']}`",
        f"- Statuses: `{', '.join(benchmark['statuses'])}`",
        "",
        "## Findings",
    ]
    findings: list[str] = []
    for idx, metrics in enumerate(metrics_by_run, start=1):
        for error in metrics.get("errors", [])[:3]:
            findings.append(f"run-{idx:03d}: {error}")
    lines.append(render_markdown_list(findings).rstrip())
    lines.append("")
    return "\n".join(lines)


def render_suite_report_markdown(report: dict[str, Any]) -> str:
    """Render suite report as markdown."""
    lines = [
        "# X News Eval Suite Report",
        "",
        f"- Overall: `{report['overall_status']}`",
        "",
        "## Skills",
    ]
    for row in report.get("skills", []):
        lines.extend(
            [
                f"- `{row['skill']}`: `{row['status']}`",
                f"  benchmark: `{row.get('benchmark_path', 'N/A')}`",
            ]
        )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Compare invocations
# ---------------------------------------------------------------------------


def compare_invocations(path_a: Path, path_b: Path) -> dict[str, Any]:
    """Compare two eval invocations."""

    def load_metrics(p: Path) -> dict[str, Any]:
        metrics_path = p / "metrics.json"
        if metrics_path.exists():
            return load_json(metrics_path)
        return {}

    def load_judge(p: Path) -> dict[str, Any]:
        judge_path = p / "judge.json"
        if judge_path.exists():
            return load_json(judge_path)
        return {}

    metrics_a = load_metrics(path_a)
    metrics_b = load_metrics(path_b)
    judge_a = load_judge(path_a)
    judge_b = load_judge(path_b)

    comparison: dict[str, Any] = {
        "path_a": str(path_a),
        "path_b": str(path_b),
        "metrics_a": metrics_a,
        "metrics_b": metrics_b,
        "status_a": metrics_a.get("status", "UNKNOWN"),
        "status_b": metrics_b.get("status", "UNKNOWN"),
        "same_status": metrics_a.get("status") == metrics_b.get("status"),
    }

    # Compare candidate IDs for pipeline
    if "candidate_ids" in metrics_a and "candidate_ids" in metrics_b:
        ids_a = set(metrics_a["candidate_ids"])
        ids_b = set(metrics_b["candidate_ids"])
        comparison["candidate_jaccard"] = (
            len(ids_a & ids_b) / len(ids_a | ids_b) if ids_a | ids_b else None
        )

    # Compare selected IDs for editorial
    if "selected_ids" in metrics_a and "selected_ids" in metrics_b:
        ids_a = set(metrics_a["selected_ids"])
        ids_b = set(metrics_b["selected_ids"])
        comparison["selected_jaccard"] = (
            len(ids_a & ids_b) / len(ids_a | ids_b) if ids_a | ids_b else None
        )

    return comparison


# ---------------------------------------------------------------------------
# Case discovery
# ---------------------------------------------------------------------------


def list_skill_cases(skill: str) -> list[dict[str, Any]]:
    """List all available cases for a skill."""
    cases_dir = EVAL_ROOT / "cases" / skill
    if not cases_dir.exists():
        return []
    cases = []
    for path in cases_dir.glob("*.json"):
        try:
            case = load_json(path)
            cases.append(case)
        except (json.JSONDecodeError, FileNotFoundError):
            continue
    return sorted(cases, key=lambda c: c.get("report_date", ""))


def list_suites() -> list[dict[str, Any]]:
    """List all available suites."""
    suites_dir = EVAL_ROOT / "cases" / "suites"
    if not suites_dir.exists():
        return []
    suites = []
    for path in suites_dir.glob("*.json"):
        try:
            suite = load_json(path)
            suites.append(suite)
        except (json.JSONDecodeError, FileNotFoundError):
            continue
    return sorted(suites, key=lambda s: s.get("report_date", ""))
