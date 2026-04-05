#!/usr/bin/env python3
"""
High-level eval operations for x-news-skills.

Provides operations like analyze_stage, diagnose_daily, and rerun_stage.
"""

from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from eval_lib import (
    EVAL_ROOT,
    EVAL_RUNS_ROOT,
    REPO_ROOT,
    build_benchmark,
    compare_invocations,
    create_invocation_paths,
    ensure_dir,
    evaluate_data_pipeline_run,
    evaluate_daily_post_run,
    evaluate_editorial_run,
    load_case,
    load_suite,
    list_skill_cases,
    list_suites,
    render_skill_analysis,
    render_suite_report_markdown,
    short_id,
    stage_fixtures,
    write_json,
)

# Skill order for suite runs
SKILL_ORDER = ["x-news-data-pipeline", "x-news-editorial", "x-news-to-daily-post"]

# Stage aliases
STAGE_ALIAS = {
    "pipeline": "x-news-data-pipeline",
    "data-pipeline": "x-news-data-pipeline",
    "data_pipeline": "x-news-data-pipeline",
    "editorial": "x-news-editorial",
    "daily-post": "x-news-to-daily-post",
    "daily_post": "x-news-to-daily-post",
    "dailypost": "x-news-to-daily-post",
}


def normalize_stage(value: str) -> str:
    """Normalize a stage name to full skill name."""
    if value in STAGE_ALIAS:
        return STAGE_ALIAS[value]
    if value in {*STAGE_ALIAS.values()}:
        return value
    # Try partial match
    for alias, full in STAGE_ALIAS.items():
        if alias in value.lower():
            return full
    return value


def find_case_for_date(stage: str, report_date: str) -> tuple[dict[str, Any] | None, Path | None]:
    """Find a case for a given stage and date.

    Looks for a case file with report_date matching.
    """
    cases = list_skill_cases(stage)
    for case in reversed(cases):  # Prefer newer cases
        if case.get("report_date") == report_date:
            return case, EVAL_ROOT / "cases" / stage / f"{case['id']}.json"
    # Fall back to latest case
    if cases:
        latest = cases[-1]
        return latest, EVAL_ROOT / "cases" / stage / f"{latest['id']}.json"
    return None, None


def resolve_invocation_ref(value: str) -> Path | None:
    """Resolve a date or path reference to an invocation directory.

    If value looks like a date (YYYY-MM-DD), find the most recent invocation.
    Otherwise treat as a path.
    """
    import re
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        # It's a date - find most recent invocation
        date_dir = EVAL_RUNS_ROOT / value
        if not date_dir.exists():
            return None
        invocations = sorted(date_dir.iterdir(), reverse=True)
        if invocations:
            return invocations[0]
        return None
    path = Path(value)
    if path.exists():
        return path
    return None


# ---------------------------------------------------------------------------
# Fixture copy evaluation
# ---------------------------------------------------------------------------

def run_fixture_evaluation(
    skill: str,
    case: dict[str, Any],
    invocation_paths,
) -> dict[str, Any]:
    """Run evaluation using fixture_copy mode.

    Copies fixtures to artifacts directory and runs evaluation.
    """
    artifacts_dir = ensure_dir(invocation_paths.results_dir / "artifacts")

    # Copy fixtures
    try:
        stage_fixtures(case, artifacts_dir)
    except FileNotFoundError as exc:
        write_json(invocation_paths.results_dir / "error.json", {
            "error": str(exc),
            "stage": skill,
        })
        return {"status": "ERROR", "error": str(exc)}

    # Run evaluation based on skill
    if skill == "x-news-data-pipeline":
        metrics = evaluate_data_pipeline_run(invocation_paths.results_dir)
    elif skill == "x-news-editorial":
        metrics = evaluate_editorial_run(invocation_paths.results_dir)
    elif skill == "x-news-to-daily-post":
        metrics = evaluate_daily_post_run(invocation_paths.results_dir)
    else:
        metrics = {"skill": skill, "status": "ERROR", "errors": [f"Unknown skill: {skill}"]}

    return metrics


# ---------------------------------------------------------------------------
# Single stage analysis
# ---------------------------------------------------------------------------

def analyze_stage(
    stage: str,
    report_date: str,
    case_id: str | None = None,
    runs: int = 8,
    from_run: Path | None = None,
) -> dict[str, Any]:
    """Analyze a single stage.

    Args:
        stage: Skill/stage name (e.g., "editorial", "pipeline")
        report_date: Report date (YYYY-MM-DD)
        case_id: Optional specific case ID
        runs: Number of runs (default 8)
        from_run: Optional invocation to replay from

    Returns:
        Analysis result with benchmark and path
    """
    stage = normalize_stage(stage)

    # Find case
    if case_id:
        case, case_path = load_case(stage, case_id)
    else:
        case, case_path = find_case_for_date(stage, report_date)
        if case is None:
            return {"error": f"No case found for {stage}/{report_date}"}

    # Create invocation paths
    invocation_paths = create_invocation_paths(report_date, "fixture")

    # Write case snapshot
    write_json(invocation_paths.request_dir / "case.json", case)

    # Run evaluations
    metrics_by_run = []
    for i in range(runs):
        run_dir = ensure_dir(invocation_paths.results_dir / f"run-{i+1:03d}")
        metrics = run_fixture_evaluation(stage, case, invocation_paths)
        # Re-evaluate to write metrics to correct run dir
        if metrics.get("status") not in ("ERROR",):
            # Metrics already written by run_fixture_evaluation
            pass
        metrics_by_run.append(metrics)

    # Build benchmark
    benchmark = build_benchmark(stage, case, metrics_by_run)

    # Write benchmark
    benchmark_path = invocation_paths.results_dir / "benchmark.json"
    write_json(benchmark_path, benchmark)

    # Render analysis
    analysis_text = render_skill_analysis(stage, case, benchmark, metrics_by_run)
    analysis_path = invocation_paths.results_dir / "analysis.md"
    analysis_path.write_text(analysis_text, encoding="utf-8")

    return {
        "skill": stage,
        "case_id": case["id"],
        "report_date": report_date,
        "invocation_path": str(invocation_paths.root),
        "benchmark_path": str(benchmark_path),
        "analysis_path": str(analysis_path),
        "runs": runs,
        "benchmark": benchmark,
        "metrics_by_run": metrics_by_run,
    }


# ---------------------------------------------------------------------------
# Daily diagnosis
# ---------------------------------------------------------------------------

def diagnose_daily(report_date: str) -> dict[str, Any]:
    """Diagnose all stages for a given daily run.

    Args:
        report_date: Report date (YYYY-MM-DD)

    Returns:
        Diagnosis result with per-skill analysis
    """
    results: dict[str, Any] = {
        "report_date": report_date,
        "skills": {},
    }

    for skill in SKILL_ORDER:
        result = analyze_stage(skill, report_date, runs=1)
        if "error" in result:
            results["skills"][skill] = {"error": result["error"]}
        else:
            results["skills"][skill] = {
                "invocation_path": result.get("invocation_path"),
                "benchmark": result.get("benchmark", {}),
            }

    # Determine overall status
    all_pass = all(
        r.get("benchmark", {}).get("fail_count", 1) == 0
        for r in results["skills"].values()
        if "benchmark" in r
    )
    results["overall_status"] = "PASS" if all_pass else "FAIL"

    return results


# ---------------------------------------------------------------------------
# Suite run
# ---------------------------------------------------------------------------

def run_suite(suite_id: str, runs: int = 8) -> dict[str, Any]:
    """Run a full suite evaluation.

    Args:
        suite_id: Suite identifier (e.g., "suite-2026-04-01")
        runs: Number of runs per stage

    Returns:
        Suite result with per-skill summaries
    """
    suite, suite_path = load_suite(suite_id)
    report_date = suite.get("report_date", "")

    skill_summaries: dict[str, dict[str, Any]] = {}

    for skill in SKILL_ORDER:
        case_id = suite.get("skills", {}).get(skill)
        if not case_id:
            continue

        case_path_candidate = EVAL_ROOT / "cases" / skill / f"{case_id}.json"
        if not case_path_candidate.exists():
            skill_summaries[skill] = {"error": f"Case not found: {case_id}"}
            continue

        result = analyze_stage(skill, report_date, case_id=case_id, runs=runs)
        skill_summaries[skill] = {
            "invocation_path": result.get("invocation_path"),
            "benchmark": result.get("benchmark"),
            "analysis": result.get("analysis_path"),
        }

    # Build suite report
    overall_status = "PASS"
    skill_rows = []

    for skill in SKILL_ORDER:
        summary = skill_summaries.get(skill, {})
        if "error" in summary:
            overall_status = "FAIL"
            skill_rows.append({"skill": skill, "status": "ERROR", "error": summary["error"]})
            continue

        benchmark = summary.get("benchmark", {})
        status = "FAIL" if benchmark.get("fail_count", 0) else "WARN" if benchmark.get("warn_count", 0) else "PASS"
        if status == "FAIL":
            overall_status = "FAIL"
        elif status == "WARN" and overall_status == "PASS":
            overall_status = "WARN"

        skill_rows.append({
            "skill": skill,
            "status": status,
            "benchmark_path": summary.get("invocation_path", ""),
            "analysis_path": summary.get("analysis", ""),
        })

    suite_report = {
        "overall_status": overall_status,
        "skills": skill_rows,
        "suite_id": suite_id,
        "report_date": report_date,
        "runs": runs,
    }

    # Write suite report
    invocation_paths = create_invocation_paths(report_date, f"suite-{short_id()}")
    write_json(invocation_paths.summary_dir / "report.json", suite_report)

    report_md = render_suite_report_markdown(suite_report)
    (invocation_paths.summary_dir / "report.md").write_text(report_md, encoding="utf-8")

    return suite_report


# ---------------------------------------------------------------------------
# Compare invocations
# ---------------------------------------------------------------------------

def compare_invocations(path_a: str | Path, path_b: str | Path) -> dict[str, Any]:
    """Compare two eval invocations.

    Args:
        path_a: First invocation path or date reference
        path_b: Second invocation path or date reference

    Returns:
        Comparison result
    """
    from eval_lib import compare_invocations as lib_compare

    # Resolve paths if they're dates
    resolved_a = resolve_invocation_ref(str(path_a)) if not Path(str(path_a)).exists() else Path(str(path_a))
    resolved_b = resolve_invocation_ref(str(path_b)) if not Path(str(path_b)).exists() else Path(str(path_b))

    if not resolved_a:
        return {"error": f"Cannot resolve path_a: {path_a}"}
    if not resolved_b:
        return {"error": f"Cannot resolve path_b: {path_b}"}

    return lib_compare(resolved_a, resolved_b)


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------

def history_table(stage: str | None = None, limit: int = 20) -> str:
    """Generate markdown table of historical invocations.

    Args:
        stage: Optional stage filter
        limit: Maximum number of entries

    Returns:
        Markdown table string
    """
    if not EVAL_RUNS_ROOT.exists():
        return "# No eval runs found\n"

    rows = []
    for date_dir in sorted(EVAL_RUNS_ROOT.iterdir(), reverse=True)[:limit]:
        if not date_dir.is_dir():
            continue
        for invocation_dir in sorted(date_dir.iterdir(), reverse=True):
            if not invocation_dir.is_dir():
                continue
            metrics_path = invocation_dir / "results" / "metrics.json"
            if not metrics_path.exists():
                # Try in results/run-NNN/metrics.json
                results_dir = invocation_dir / "results"
                if results_dir.exists():
                    for run_dir in sorted(results_dir.glob("run-*/metrics.json"), reverse=True):
                        metrics_path = run_dir
                        break
            if not metrics_path.exists():
                continue
            try:
                metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue

            skill = metrics.get("skill", "unknown")
            if stage and normalize_stage(stage) != skill:
                continue

            status = metrics.get("status", "UNKNOWN")
            errors = metrics.get("errors", [])
            error_preview = errors[0][:50] if errors else ""

            rows.append([
                date_dir.name,
                invocation_dir.name,
                skill,
                f"`{status}`",
                error_preview,
            ])

    if not rows:
        return "# No eval runs found\n"

    header = "| Date | Invocation | Skill | Status | Error |\n|--------|-----------|-------|--------|-------|\n"
    lines = ["# Eval History\n", header]
    for row in rows[:limit]:
        lines.append(f"| {' | '.join(str(c) for c in row)} |")

    return "\n".join(lines) + "\n"
